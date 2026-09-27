import asyncio
import json
from datetime import UTC, datetime

import pytest

from domain import AgentDefinition, AgentRequest, AgentResult
from workspaces.data_engineering.agents.prod_support import (
    AirflowFailure,
    InvestigationServices,
    ProdSupportAgent,
)
from workspaces.data_engineering.agents.prod_support.models import Region
from workspaces.data_engineering.agents.prod_support.ports import (
    TaskLogUnavailableError,
)
from workspaces.data_engineering.agents.resource_discovery import (
    ResourceDiscoveryAgent,
    ResourceIdentifier,
)


class FakeAirflow:
    def __init__(self, failures: tuple[AirflowFailure, ...]) -> None:
        self.failures = failures

    async def discover_failures(self, since: datetime) -> tuple[AirflowFailure, ...]:
        del since
        return self.failures

    async def fetch_log(self, failure: AirflowFailure) -> str:
        return failure.log


class UnavailableLogAirflow(FakeAirflow):
    def __init__(
        self,
        failures: tuple[AirflowFailure, ...],
        status_code: int,
    ) -> None:
        super().__init__(failures)
        self.status_code = status_code

    async def fetch_log(self, failure: AirflowFailure) -> str:
        raise TaskLogUnavailableError(failure.failure_id, self.status_code)


class ExactLogAirflow(FakeAirflow):
    def __init__(
        self,
        failures: tuple[AirflowFailure, ...],
        exact_log: str,
    ) -> None:
        super().__init__(failures)
        self.exact_log = exact_log
        self.fetched: list[str] = []

    async def fetch_log(self, failure: AirflowFailure) -> str:
        self.fetched.append(failure.failure_id)
        return self.exact_log


class FakeResourceSource:
    def __init__(self) -> None:
        self.identifiers: list[ResourceIdentifier] = []

    async def lookup(
        self,
        identifier: ResourceIdentifier,
    ) -> tuple[dict[str, object], ...]:
        self.identifiers.append(identifier)
        return (
            {
                "provisioned_client_id": identifier.value,
                "client_name": "Example Bank",
                "environment": "production",
            },
        )


class FakeReportRuntime:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run(
        self,
        definition: AgentDefinition,
        request: AgentRequest,
    ) -> AgentResult:
        self.calls.append(definition.name)
        return AgentResult(
            output=json.dumps(
                {
                    "developer": (
                        "Message for developer:\n"
                        "  - US Cluster Health: healthy\n"
                        "  - CA Cluster Health: healthy"
                    ),
                    "data_internal": (
                        ":bangbang: PROD SUPPORT 2026-09-24 :bangbang:\n"
                        "US\n- Good\nCA\n- Good"
                    ),
                    "follow_up": "- No action is required.",
                }
            ),
            correlation_id=request.correlation_id,
        )


def failure(day: int, log: str) -> AirflowFailure:
    return AirflowFailure(
        region=Region.US_01,
        dag_id=f"dag-{day}",
        run_id=f"run-{day}",
        task_id="task",
        start_at=datetime(2026, 9, day, 5, tzinfo=UTC),
        end_at=datetime(2026, 9, day, 6, tzinfo=UTC),
        log=log,
    )


def test_agent_filters_prior_day_and_classifies_logs() -> None:
    agent = ProdSupportAgent(
        FakeAirflow(
            (
                failure(23, "old failure"),
                failure(24, "OOMKilled by container"),
            )
        ),
        clock=lambda: datetime(2026, 9, 25, 12, tzinfo=UTC),
    )

    outcome = asyncio.run(agent.investigate("do today's prod support"))

    assert [item.dag_id for item in outcome.failures] == ["dag-24"]
    assert outcome.diagnoses[0].kind.value == "confirmed_oom"
    assert "PROD SUPPORT 2026-09-24" in outcome.report


def test_agent_honors_us_only_scope() -> None:
    us_failure = failure(24, "OOMKilled by container")
    ca_failure = AirflowFailure(
        region=Region.CA_02,
        dag_id="ca-dag",
        run_id="ca-run",
        task_id="ca-task",
        start_at=datetime(2026, 9, 24, 5, tzinfo=UTC),
        end_at=datetime(2026, 9, 24, 6, tzinfo=UTC),
        log="failed",
    )
    agent = ProdSupportAgent(
        FakeAirflow((us_failure, ca_failure)),
        clock=lambda: datetime(2026, 9, 25, 12, tzinfo=UTC),
    )

    outcome = asyncio.run(agent.investigate("Do US Prod Support"))

    assert outcome.regions == (Region.US_01,)
    assert outcome.failures == (us_failure,)
    assert "airflow-us01.precisionlender.com" in outcome.report
    assert "airflow-ca02.precisionlender.com" not in outcome.report
    assert "\nCA\n" not in outcome.data_internal_report


def test_agent_normalizes_framework_result() -> None:
    agent = ProdSupportAgent(
        FakeAirflow(()),
        clock=lambda: datetime(2026, 9, 25, 12, tzinfo=UTC),
    )

    result = asyncio.run(
        agent.run(AgentRequest("do prod support", correlation_id="case-1"))
    )

    assert result.correlation_id == "case-1"
    assert dict(result.attributes)["failure_count"] == 0
    assert dict(result.attributes)["resource_discovery_count"] == 0
    assert dict(result.attributes)["regions"] == "US-01,CA-02"


def test_agent_uses_one_reporting_call() -> None:
    runtime = FakeReportRuntime()
    unknown = failure(24, "")
    agent = ProdSupportAgent(
        UnavailableLogAirflow((unknown,), 404),
        clock=lambda: datetime(2026, 9, 25, 12, tzinfo=UTC),
        investigation=InvestigationServices(report_runtime=runtime),
    )

    outcome = asyncio.run(agent.investigate("do prod support", correlation_id="case-1"))

    assert outcome.developer_report.endswith("CA Cluster Health: healthy")
    assert runtime.calls == ["prod-support.reporting"]


def test_agent_definition_requires_operational_delivery_workflow() -> None:
    definition = ProdSupportAgent(FakeAirflow(())).definition

    assert "Do US prod support" in definition.instructions
    assert "Do CA prod support" in definition.instructions
    assert "previous operational day" in definition.instructions
    assert "cluster-health and Airflow checks concurrently" in definition.instructions
    assert "D2P or MI3" in definition.instructions
    assert "No component may delegate further" in definition.instructions
    assert definition.can_delegate is True
    assert "inspect_cluster_health" in {tool.name for tool in definition.tools}
    assert "trigger_resource_discovery_agent" in {
        tool.name for tool in definition.tools
    }
    assert definition.version == "17"
    assert definition.output_template is not None
    assert definition.output_template.startswith("# Prod Support Report")


def test_agent_reports_missing_task_log_as_developer_evidence_gap() -> None:
    missing_log = failure(24, "")
    agent = ProdSupportAgent(
        UnavailableLogAirflow((missing_log,), 404),
        clock=lambda: datetime(2026, 9, 25, 12, tzinfo=UTC),
    )

    outcome = asyncio.run(agent.investigate("do today's prod support"))

    assert outcome.diagnoses[0].kind.value == "unknown"
    assert outcome.diagnoses[0].confidence == "evidence_gap"
    assert "Airflow task log unavailable: HTTP 404" in outcome.developer_report
    assert missing_log.dag_id in outcome.data_internal_report


def test_agent_still_fails_fast_for_non_404_log_errors() -> None:
    missing_log = failure(24, "")
    agent = ProdSupportAgent(
        UnavailableLogAirflow((missing_log,), 503),
        clock=lambda: datetime(2026, 9, 25, 12, tzinfo=UTC),
    )

    with pytest.raises(TaskLogUnavailableError, match="HTTP 503"):
        asyncio.run(agent.investigate("do today's prod support"))


def test_agent_triggers_resource_discovery_for_unique_resend_clients() -> None:
    client_id = "1f06da19-2f61-401c-a1b7-38902e4f3543"
    resend = AirflowFailure(
        region=Region.CA_02,
        dag_id=f"l3-main-{client_id}",
        run_id="manual__2026-09-24T05:00:00+00:00",
        task_id="validate_event_bus_opportunities",
        start_at=datetime(2026, 9, 24, 5, tzinfo=UTC),
        end_at=datetime(2026, 9, 24, 6, tzinfo=UTC),
        log="OpportunityValidationException",
    )
    source = FakeResourceSource()
    agent = ProdSupportAgent(
        FakeAirflow((resend, resend)),
        clock=lambda: datetime(2026, 9, 25, 12, tzinfo=UTC),
        resource_discovery=ResourceDiscoveryAgent(source),
    )

    outcome = asyncio.run(agent.investigate("do today's prod support"))

    assert [identifier.value for identifier in source.identifiers] == [client_id]
    assert len(outcome.resource_discovery_results) == 1
    assert "Example Bank" in outcome.developer_report
    assert dict(outcome.resource_discovery_results[0].attributes)["status"] == "unique"


def test_agent_resolves_valid_client_dags_and_skips_invalid_candidates() -> None:
    client_id = "1f06da19-2f61-401c-a1b7-38902e4f3543"
    candidates = (
        AirflowFailure(
            region=Region.CA_02,
            dag_id=f"l3-main-{client_id}",
            run_id="manual__2026-09-24T05:00:00+00:00",
            task_id="unrelated_task",
            start_at=datetime(2026, 9, 24, 5, tzinfo=UTC),
            end_at=datetime(2026, 9, 24, 6, tzinfo=UTC),
            log="failed",
        ),
        AirflowFailure(
            region=Region.CA_02,
            dag_id="unrelated-dag",
            run_id="manual__2026-09-24T05:00:00+00:00",
            task_id="validate_event_bus_opportunities",
            start_at=datetime(2026, 9, 24, 5, tzinfo=UTC),
            end_at=datetime(2026, 9, 24, 6, tzinfo=UTC),
            log="failed",
        ),
        AirflowFailure(
            region=Region.CA_02,
            dag_id="l3-main-not-a-uuid",
            run_id="manual__2026-09-24T05:00:00+00:00",
            task_id="validate_event_bus_opportunities",
            start_at=datetime(2026, 9, 24, 5, tzinfo=UTC),
            end_at=datetime(2026, 9, 24, 6, tzinfo=UTC),
            log="failed",
        ),
    )
    source = FakeResourceSource()
    agent = ProdSupportAgent(
        FakeAirflow(candidates),
        clock=lambda: datetime(2026, 9, 25, 12, tzinfo=UTC),
        resource_discovery=ResourceDiscoveryAgent(source),
    )

    outcome = asyncio.run(agent.investigate("do today's prod support"))

    assert [identifier.value for identifier in source.identifiers] == [client_id]
    assert len(outcome.resource_discovery_results) == 1


def test_agent_skips_registered_mi3_triage() -> None:
    client_id = "621d1ad2-3d0f-4fc4-8245-e3878a6bff7c"
    mi_failure = AirflowFailure(
        region=Region.US_01,
        dag_id="market_insights_3_output",
        run_id="scheduled__2026-09-24T00:00:00+00:00",
        task_id=f"client_specific.mi_3_raw_output_validation_{client_id}",
        start_at=datetime(2026, 9, 24, 5, tzinfo=UTC),
        end_at=datetime(2026, 9, 24, 6, tzinfo=UTC),
        log="pod exited 1",
    )
    source = FakeResourceSource()
    agent = ProdSupportAgent(
        FakeAirflow((mi_failure,)),
        clock=lambda: datetime(2026, 9, 25, 12, tzinfo=UTC),
        resource_discovery=ResourceDiscoveryAgent(source),
    )

    outcome = asyncio.run(agent.investigate("do today's prod support"))

    assert [identifier.value for identifier in source.identifiers] == [client_id]
    assert outcome.diagnoses[0].kind.value == "omitted"
    assert outcome.failures[0].log == ""
    assert "  - MI3" in outcome.data_internal_report


def test_agent_treats_literal_d2p_as_a_registered_omission() -> None:
    omitted = AirflowFailure(
        region=Region.US_01,
        dag_id="client-dag",
        run_id="run-24",
        task_id="D2P",
        start_at=datetime(2026, 9, 24, 5, tzinfo=UTC),
        end_at=datetime(2026, 9, 24, 6, tzinfo=UTC),
        log="discovery excerpt",
    )
    source = ExactLogAirflow((omitted,), "this should not be fetched")
    agent = ProdSupportAgent(
        source,
        clock=lambda: datetime(2026, 9, 25, 12, tzinfo=UTC),
    )

    outcome = asyncio.run(agent.investigate("Do prod support"))

    assert source.fetched == []
    assert outcome.diagnoses[0].kind.value == "omitted"
    assert "  - D2P" in outcome.data_internal_report


def test_agent_fetches_exact_log_when_discovery_contains_an_excerpt() -> None:
    discovered = failure(24, "job is still running")
    source = ExactLogAirflow((discovered,), "OOMKilled exact terminal evidence")
    agent = ProdSupportAgent(
        source,
        clock=lambda: datetime(2026, 9, 25, 12, tzinfo=UTC),
    )

    outcome = asyncio.run(agent.investigate("do today's prod support"))

    assert source.fetched == [discovered.failure_id]
    assert outcome.failures[0].log == "OOMKilled exact terminal evidence"
    assert outcome.diagnoses[0].kind.value == "confirmed_oom"


def test_agent_compacts_large_logs_after_classification() -> None:
    large_log = ("ordinary progress\n" * 10_000) + "OOMKilled terminal evidence"
    discovered = failure(24, "")
    source = ExactLogAirflow((discovered,), large_log)
    agent = ProdSupportAgent(
        source,
        clock=lambda: datetime(2026, 9, 25, 12, tzinfo=UTC),
    )

    outcome = asyncio.run(agent.investigate("do today's prod support"))
    diagnosis = outcome.diagnoses[0]

    assert outcome.failures[0].log == "OOMKilled terminal evidence"
    assert diagnosis.original_char_count == len(large_log)
    assert diagnosis.source.value == "airflow_exact_task_attempt"
    assert diagnosis.status.value == "terminal"
