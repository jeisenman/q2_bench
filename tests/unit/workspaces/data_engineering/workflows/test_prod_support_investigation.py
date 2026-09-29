import asyncio
from datetime import UTC, datetime

import pytest

from domain import AgentRequest, AgentResult
from workspaces.data_engineering.agents.oms_agent import OmsJobQueryParameters
from workspaces.data_engineering.workflows.prod_support import (
    AirflowFailure,
    AirflowTaskMetadata,
    EvidenceSource,
    InvestigationConfigurationError,
    InvestigationServices,
    PriorTaskLog,
    ProductionSupportWorkflow,
    Region,
    TaskLogUnavailableError,
)
from workspaces.data_engineering.workflows.prod_support.investigation import (
    FailureInvestigator,
)

EXPECTED_TRY_NUMBER = 2
FAILURE_COUNT = 6
TEST_PARALLELISM = 2


def _failure(
    *,
    dag_id: str = "l3-main-11111111-1111-4111-8111-111111111111",
    task_id: str = "delivery_to_promise.delivery_to_promise_data",
    end_at: datetime | None = None,
) -> AirflowFailure:
    return AirflowFailure(
        region=Region.US_01,
        dag_id=dag_id,
        run_id="manual__2026-09-25T05:00:00+00:00",
        task_id=task_id,
        start_at=datetime(2026, 9, 25, 5, tzinfo=UTC),
        end_at=end_at or datetime(2026, 9, 25, 6, tzinfo=UTC),
        try_number=2,
    )


class LogSource:
    def __init__(
        self,
        failures: tuple[AirflowFailure, ...],
        log: str = "",
        *,
        unavailable: bool = False,
    ) -> None:
        self.failures = failures
        self.log = log
        self.unavailable = unavailable
        self.fetched: list[str] = []

    async def discover_failures(self, since: datetime) -> tuple[AirflowFailure, ...]:
        del since
        return self.failures

    async def fetch_log(self, failure: AirflowFailure) -> str:
        self.fetched.append(failure.failure_id)
        if self.unavailable:
            raise TaskLogUnavailableError(failure.failure_id, 404)
        return self.log


class PriorLogs:
    def __init__(self, attempts: tuple[PriorTaskLog, ...]) -> None:
        self.attempts = attempts
        self.requests: list[tuple[str, int]] = []

    async def fetch_prior_logs(
        self,
        failure: AirflowFailure,
        limit: int,
    ) -> tuple[PriorTaskLog, ...]:
        self.requests.append((failure.failure_id, limit))
        return self.attempts


class SparkMetadata:
    async def fetch_task_metadata(
        self,
        failure: AirflowFailure,
    ) -> AirflowTaskMetadata:
        return AirflowTaskMetadata(
            dag_id=failure.dag_id,
            task_id=failure.task_id,
            operator_name="SparkSubmitOperator",
        )


class RecordingOms:
    def __init__(self, log: str) -> None:
        self.log = log
        self.parameters: list[OmsJobQueryParameters] = []

    async def query_job(self, parameters: OmsJobQueryParameters) -> str:
        self.parameters.append(parameters)
        return self.log


def test_unavailable_exact_log_uses_prior_same_task_evidence() -> None:
    failure = _failure()
    prior = PriorLogs(
        (
            PriorTaskLog(
                run_id="manual__2026-09-24T05:00:00+00:00",
                try_number=2,
                log="airflow.exceptions.AirflowTaskTimeout: Timeout",
            ),
        )
    )
    investigator = FailureInvestigator(
        LogSource((failure,), unavailable=True),
        prior_logs=prior,
    )

    _, diagnosis = asyncio.run(investigator.investigate(failure))

    assert diagnosis.kind.value == "airflow_confirmed_timeout"
    assert diagnosis.source is EvidenceSource.AIRFLOW_PRIOR_SAME_TASK
    assert diagnosis.evidence[0].startswith("prior run manual__2026-09-24")
    assert prior.requests == [(failure.failure_id, 5)]


def test_spark_uses_exact_oms_identity_to_strengthen_unknown_airflow_cause() -> None:
    failure = _failure()
    oms = RecordingOms("java.lang.OutOfMemoryError: Java heap space")
    source = LogSource((failure,), "Bash command returned exit code -9")
    investigator = FailureInvestigator(
        source,
        task_metadata=SparkMetadata(),
        oms=oms,
    )

    _, diagnosis = asyncio.run(investigator.investigate(failure))

    assert diagnosis.kind.value == "confirmed_oom"
    assert diagnosis.source is EvidenceSource.OMS_EXACT_JOB
    assert len(oms.parameters) == 1
    parameters = oms.parameters[0]
    assert parameters.client_id_g.startswith("11111111")
    assert parameters.run_id_s == failure.run_id
    assert parameters.task_id_s == failure.task_id
    assert parameters.try_number_d == EXPECTED_TRY_NUMBER
    assert source.fetched == []


def test_unresolved_oms_result_falls_back_to_airflow_log() -> None:
    failure = _failure()
    source = LogSource((failure,), "airflow.exceptions.AirflowTaskTimeout: Timeout")
    investigator = FailureInvestigator(
        source,
        task_metadata=SparkMetadata(),
        oms=RecordingOms("job started"),
    )

    _, diagnosis = asyncio.run(investigator.investigate(failure))

    assert diagnosis.kind.value == "airflow_confirmed_timeout"
    assert source.fetched == [failure.failure_id]


def test_failure_message_short_circuits_all_detailed_log_requests() -> None:
    failure = _failure()
    source = LogSource((failure,), "unused")
    investigator = FailureInvestigator(source)

    _, diagnosis = asyncio.run(
        investigator.investigate(
            AirflowFailure(
                region=failure.region,
                dag_id=failure.dag_id,
                run_id=failure.run_id,
                task_id=failure.task_id,
                start_at=failure.start_at,
                end_at=failure.end_at,
                try_number=failure.try_number,
                log="Exception: invalid source row",
            )
        )
    )

    assert diagnosis.kind.value == "application_error"
    assert diagnosis.source is EvidenceSource.AIRFLOW_FAILURE_MESSAGE
    assert source.fetched == []


def test_agent_excludes_the_operational_window_end_boundary() -> None:
    included = _failure()
    excluded = _failure(
        dag_id="l3-main-22222222-2222-4222-8222-222222222222",
        end_at=datetime(2026, 9, 26, 5, tzinfo=UTC),
    )
    agent = ProductionSupportWorkflow(
        LogSource((excluded, included), "Exception: failed"),
        clock=lambda: datetime(2026, 9, 26, 12, tzinfo=UTC),
    )

    outcome = asyncio.run(agent.investigate("Run prod support for 9/25/26"))

    assert [failure.failure_id for failure in outcome.failures] == [included.failure_id]


class IgnoredResourceDiscovery:
    async def run(self, request: AgentRequest) -> AgentResult:
        attributes = dict(request.attributes)
        return AgentResult(
            output="ignored canary",
            correlation_id=request.correlation_id,
            attributes=(
                ("identifier_value", attributes["identifier_value"]),
                ("status", "not_found"),
                ("prod_support_ignore", True),
            ),
        )


def test_agent_filters_only_explicitly_reviewed_support_ignores() -> None:
    failure = _failure(task_id="active_deposit_accounts.active_deposit_accounts")
    source = LogSource((failure,), "Exception: should not be fetched")
    agent = ProductionSupportWorkflow(
        source,
        clock=lambda: datetime(2026, 9, 26, 12, tzinfo=UTC),
        resource_discovery=IgnoredResourceDiscovery(),
    )

    outcome = asyncio.run(agent.investigate("Run prod support for 9/25/26"))

    assert outcome.failures == ()
    assert source.fetched == []


class CountingLogSource(LogSource):
    def __init__(self, failures: tuple[AirflowFailure, ...]) -> None:
        super().__init__(failures, "Exception: terminal")
        self.active = 0
        self.peak = 0

    async def fetch_log(self, failure: AirflowFailure) -> str:
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(0)
        result = await super().fetch_log(failure)
        self.active -= 1
        return result


def test_agent_respects_configured_parallelism() -> None:
    failures = tuple(_failure(dag_id=f"dag-{index}") for index in range(FAILURE_COUNT))
    source = CountingLogSource(failures)
    agent = ProductionSupportWorkflow(
        source,
        clock=lambda: datetime(2026, 9, 26, 12, tzinfo=UTC),
        investigation=InvestigationServices(max_parallel=TEST_PARALLELISM),
    )

    outcome = asyncio.run(agent.investigate("Run prod support for 9/25/26"))

    assert len(outcome.failures) == FAILURE_COUNT
    assert source.peak <= TEST_PARALLELISM


def test_investigation_rejects_parallelism_below_one() -> None:
    with pytest.raises(InvestigationConfigurationError, match="at least 1"):
        InvestigationServices(max_parallel=0)
    with pytest.raises(InvestigationConfigurationError, match="at least 1"):
        InvestigationServices(max_parallel=-1)


def test_investigation_allows_io_fan_out_above_the_former_cap() -> None:
    # max_parallel bounds outbound API concurrency only. Agent-loop
    # parallelism is owned by the harness, so there is no ceiling here.
    high_fan_out = 12
    assert InvestigationServices(max_parallel=high_fan_out).max_parallel == (
        high_fan_out
    )


def test_prior_task_log_rejects_invalid_identity() -> None:
    with pytest.raises(ValueError, match="run_id must not be empty"):
        PriorTaskLog(run_id="", try_number=1, log="")
    with pytest.raises(ValueError, match="try_number must be positive"):
        PriorTaskLog(run_id="run", try_number=0, log="")
