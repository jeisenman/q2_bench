"""Short-circuiting evidence retrieval for production failures."""

from __future__ import annotations

from dataclasses import dataclass, replace

from agent_memory import AgentMemory
from workspaces.data_engineering.agents.oms_agent import (
    OmsEvidenceUnavailableError,
    OmsJobEvidenceSource,
    OmsJobQueryParameters,
)
from workspaces.data_engineering.workflows.prod_support.classification import (
    classify_log,
)
from workspaces.data_engineering.workflows.prod_support.evidence import (
    summarize_task_log,
)
from workspaces.data_engineering.workflows.prod_support.models import (
    AirflowFailure,
    EvidenceSource,
    EvidenceStatus,
    FailureDiagnosis,
    FailureKind,
    PriorTaskLog,
)
from workspaces.data_engineering.workflows.prod_support.ports import (
    AirflowFailureSource,
    AirflowTaskMetadataSource,
    PriorTaskLogSource,
    TaskLogUnavailableError,
)
from workspaces.data_engineering.workflows.prod_support.reporting_details import (
    client_id,
)
from workspaces.data_engineering.workflows.prod_support.workloads import (
    WorkloadKind,
    classify_workload,
)

TASK_LOG_NOT_FOUND = 404
PRIOR_LOG_LIMIT = 5
DEFAULT_MAX_PARALLEL = 5


class InvestigationConfigurationError(ValueError):
    """Raised when evidence investigation settings are unsafe."""

    @classmethod
    def invalid_parallelism(cls, value: int) -> InvestigationConfigurationError:
        """Return an error for non-positive I/O concurrency."""
        return cls(f"max_parallel must be at least 1; got {value}")


@dataclass(frozen=True, slots=True)
class InvestigationServices:
    """Optional exact-evidence services and concurrency settings."""

    prior_logs: PriorTaskLogSource | None = None
    task_metadata: AirflowTaskMetadataSource | None = None
    oms: OmsJobEvidenceSource | None = None
    memory: AgentMemory | None = None
    max_parallel: int = DEFAULT_MAX_PARALLEL

    def __post_init__(self) -> None:
        """Reject a concurrency bound that cannot run any work."""
        if self.max_parallel < 1:
            raise InvestigationConfigurationError.invalid_parallelism(self.max_parallel)


class FailureInvestigator:
    """Retrieve compact Airflow and optional OMS evidence for one failure."""

    def __init__(
        self,
        source: AirflowFailureSource,
        *,
        prior_logs: PriorTaskLogSource | None = None,
        task_metadata: AirflowTaskMetadataSource | None = None,
        oms: OmsJobEvidenceSource | None = None,
    ) -> None:
        """Initialize read-only evidence dependencies."""
        self._source = source
        self._prior_logs = prior_logs
        self._task_metadata = task_metadata
        self._oms = oms

    async def investigate(
        self,
        failure: AirflowFailure,
    ) -> tuple[AirflowFailure, FailureDiagnosis]:
        """Use the cheapest conclusive evidence before fetching detailed logs."""
        message_result = _failure_message_result(failure)
        if message_result is not None and not _needs_prior(message_result[1]):
            return message_result
        if await self._is_spark(failure) and self._oms is not None:
            identifier = client_id(failure)
            if identifier is not None:
                return await self._investigate_spark(failure, identifier)
        return await self._investigate_airflow(failure)

    async def _is_spark(self, failure: AirflowFailure) -> bool:
        """Return whether exact Airflow metadata proves a Spark workload."""
        if self._task_metadata is None:
            return False
        metadata = await self._task_metadata.fetch_task_metadata(failure)
        return classify_workload(metadata) is WorkloadKind.SPARK_BATCH

    async def _investigate_spark(
        self,
        failure: AirflowFailure,
        identifier: str,
    ) -> tuple[AirflowFailure, FailureDiagnosis]:
        """Use exact OMS evidence first and fetch Airflow logs only if unresolved."""
        try:
            oms_result = await self._query_oms(failure, identifier)
        except OmsEvidenceUnavailableError:
            return await self._investigate_airflow(failure)
        if not _needs_prior(oms_result[1]):
            return oms_result
        airflow_result = await self._investigate_airflow(failure)
        return _prefer_stronger_evidence(airflow_result, oms_result)

    async def _query_oms(
        self,
        failure: AirflowFailure,
        identifier: str,
    ) -> tuple[AirflowFailure, FailureDiagnosis]:
        """Query and classify one exact OMS job attempt."""
        if self._oms is None:
            raise OmsEvidenceUnavailableError.not_configured()
        parameters = OmsJobQueryParameters(
            region=failure.region,
            client_id_g=identifier,
            run_id_s=failure.run_id,
            task_id_s=failure.task_id,
            try_number_d=failure.try_number,
            start_at=failure.start_at,
        )
        log = await self._oms.query_job(parameters)
        return _classified_result(failure, log, EvidenceSource.OMS_EXACT_JOB)

    async def _investigate_airflow(
        self,
        failure: AirflowFailure,
    ) -> tuple[AirflowFailure, FailureDiagnosis]:
        """Fetch the exact attempt, then use bounded same-task history."""
        try:
            log = await self._source.fetch_log(failure)
        except TaskLogUnavailableError as error:
            if error.status_code != TASK_LOG_NOT_FOUND:
                raise
            prior = await self._first_diagnostic_prior(failure)
            return prior or _unavailable_result(failure)
        result = _classified_result(
            failure,
            log,
            EvidenceSource.AIRFLOW_EXACT_TASK_ATTEMPT,
        )
        if _needs_prior(result[1]):
            prior = await self._first_diagnostic_prior(failure)
            if prior is not None:
                return prior
        return result

    async def _first_diagnostic_prior(
        self,
        failure: AirflowFailure,
    ) -> tuple[AirflowFailure, FailureDiagnosis] | None:
        """Return the first diagnostic prior attempt for the same task."""
        if self._prior_logs is None:
            return None
        attempts = await self._prior_logs.fetch_prior_logs(failure, PRIOR_LOG_LIMIT)
        for attempt in attempts:
            result = _prior_result(failure, attempt)
            if not _needs_prior(result[1]):
                return result
        return None


def _classified_result(
    failure: AirflowFailure,
    log: str,
    source: EvidenceSource,
) -> tuple[AirflowFailure, FailureDiagnosis]:
    """Classify a full log and retain only bounded diagnostic evidence."""
    summary = summarize_task_log(log)
    diagnosis = classify_log(failure, log, source=source)
    hydrated = replace(failure, log=summary.excerpt)
    return hydrated, replace(diagnosis, status=summary.status)


def _failure_message_result(
    failure: AirflowFailure,
) -> tuple[AirflowFailure, FailureDiagnosis] | None:
    """Classify a discovery-provided failure message without another API call."""
    if not failure.log.strip():
        return None
    return _classified_result(
        failure,
        failure.log,
        EvidenceSource.AIRFLOW_FAILURE_MESSAGE,
    )


def _prior_result(
    failure: AirflowFailure,
    attempt: PriorTaskLog,
) -> tuple[AirflowFailure, FailureDiagnosis]:
    """Classify one prior same-task attempt and attach its provenance."""
    hydrated, diagnosis = _classified_result(
        failure,
        attempt.log,
        EvidenceSource.AIRFLOW_PRIOR_SAME_TASK,
    )
    provenance = f"prior run {attempt.run_id} attempt {attempt.try_number}"
    return hydrated, replace(
        diagnosis,
        evidence=(provenance, *diagnosis.evidence)[:3],
    )


def _unavailable_result(
    failure: AirflowFailure,
) -> tuple[AirflowFailure, FailureDiagnosis]:
    """Return an explicit exact-log evidence gap."""
    diagnosis = FailureDiagnosis(
        failure_id=failure.failure_id,
        kind=FailureKind.UNKNOWN,
        confidence="evidence_gap",
        evidence=("Airflow task log unavailable: HTTP 404",),
        source=EvidenceSource.AIRFLOW_EXACT_TASK_ATTEMPT,
        status=EvidenceStatus.UNAVAILABLE,
    )
    return failure, diagnosis


def _needs_prior(diagnosis: FailureDiagnosis) -> bool:
    """Return whether current evidence lacks a supported terminal cause."""
    return diagnosis.kind is FailureKind.UNKNOWN or diagnosis.status in {
        EvidenceStatus.NON_DIAGNOSTIC,
        EvidenceStatus.TRUNCATED,
        EvidenceStatus.UNAVAILABLE,
    }


def _prefer_stronger_evidence(
    airflow: tuple[AirflowFailure, FailureDiagnosis],
    oms: tuple[AirflowFailure, FailureDiagnosis],
) -> tuple[AirflowFailure, FailureDiagnosis]:
    """Prefer OMS only when it improves an unsupported Airflow diagnosis."""
    airflow_kind = airflow[1].kind
    oms_kind = oms[1].kind
    if oms_kind is FailureKind.UNKNOWN:
        return airflow
    if airflow_kind in {
        FailureKind.UNKNOWN,
        FailureKind.UNKNOWN_RESOURCE_TERMINATION,
        FailureKind.PROBABLE_OOM,
    }:
        return oms
    return airflow
