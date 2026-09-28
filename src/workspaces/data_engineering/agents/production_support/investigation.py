"""Short-circuiting evidence retrieval for production failures."""

from __future__ import annotations

from dataclasses import dataclass, replace

from agent_memory import AgentMemory
from ports import AgentRuntime
from workspaces.data_engineering.agents.oms_agent import (
    OmsEvidenceUnavailableError,
    OmsJobEvidenceSource,
    OmsJobQueryParameters,
)
from workspaces.data_engineering.agents.production_support.classification_agent import (
    ClassificationAgent,
)
from workspaces.data_engineering.agents.production_support.evidence import (
    summarize_task_log,
)
from workspaces.data_engineering.agents.production_support.failure_tools import (
    ExactLogTool,
)
from workspaces.data_engineering.agents.production_support.models import (
    AirflowFailure,
    EvidenceSource,
    EvidenceStatus,
    FailureDiagnosis,
    FailureKind,
    PriorTaskLog,
)
from workspaces.data_engineering.agents.production_support.ports import (
    AirflowFailureSource,
    AirflowTaskMetadataSource,
    PriorTaskLogSource,
    TaskLogUnavailableError,
)
from workspaces.data_engineering.agents.production_support.reporting_details import (
    client_id,
)
from workspaces.data_engineering.agents.production_support.workloads import (
    WorkloadKind,
    classify_workload,
)

TASK_LOG_NOT_FOUND = 404
PRIOR_LOG_LIMIT = 5
MAX_PARALLEL_LIMIT = 5


class InvestigationConfigurationError(ValueError):
    """Raised when evidence investigation settings are unsafe."""

    @classmethod
    def invalid_parallelism(cls) -> InvestigationConfigurationError:
        """Return an error for unsupported worker parallelism."""
        return cls("max_parallel must be between 1 and 5")


@dataclass(frozen=True, slots=True)
class InvestigationServices:
    """Optional exact-evidence services and concurrency settings."""

    prior_logs: PriorTaskLogSource | None = None
    task_metadata: AirflowTaskMetadataSource | None = None
    oms: OmsJobEvidenceSource | None = None
    report_runtime: AgentRuntime | None = None
    memory: AgentMemory | None = None
    max_parallel: int = MAX_PARALLEL_LIMIT

    def __post_init__(self) -> None:
        """Reject unsafe subagent-style parallelism."""
        if not 1 <= self.max_parallel <= MAX_PARALLEL_LIMIT:
            raise InvestigationConfigurationError.invalid_parallelism()


class FailureInvestigator:
    """Retrieve compact Airflow and optional OMS evidence for one failure."""

    def __init__(
        self,
        source: AirflowFailureSource,
        *,
        prior_logs: PriorTaskLogSource | None = None,
        task_metadata: AirflowTaskMetadataSource | None = None,
        oms: OmsJobEvidenceSource | None = None,
        classifier: ClassificationAgent | None = None,
    ) -> None:
        """Initialize read-only evidence dependencies."""
        self._source = source
        self._exact_log = ExactLogTool(source)
        self._prior_logs = prior_logs
        self._task_metadata = task_metadata
        self._oms = oms
        self._classifier = classifier or ClassificationAgent()

    async def investigate(
        self,
        failure: AirflowFailure,
    ) -> tuple[AirflowFailure, FailureDiagnosis]:
        """Fetch the exact log, then stop when its evidence is conclusive."""
        airflow_result = await self._investigate_airflow(failure)
        if not _needs_prior(airflow_result[1]):
            return airflow_result
        if await self._is_spark(failure) and self._oms is not None:
            identifier = client_id(failure)
            if identifier is not None:
                return await self._investigate_spark(
                    failure,
                    identifier,
                    airflow_result,
                )
        return airflow_result

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
        airflow_result: tuple[AirflowFailure, FailureDiagnosis],
    ) -> tuple[AirflowFailure, FailureDiagnosis]:
        """Use exact OMS evidence only after Airflow remains unresolved."""
        try:
            oms_result = await self._query_oms(failure, identifier)
        except OmsEvidenceUnavailableError:
            return airflow_result
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
        return _classified_result(
            failure,
            log,
            EvidenceSource.OMS_EXACT_JOB,
            self._classifier,
        )

    async def _investigate_airflow(
        self,
        failure: AirflowFailure,
    ) -> tuple[AirflowFailure, FailureDiagnosis]:
        """Fetch the exact attempt, then use bounded same-task history."""
        try:
            log = await self._exact_log.fetch(failure)
        except TaskLogUnavailableError as error:
            if error.status_code != TASK_LOG_NOT_FOUND:
                raise
            prior = await self._first_diagnostic_prior(failure)
            return prior or _unavailable_result(failure)
        result = _classified_result(
            failure,
            log,
            EvidenceSource.AIRFLOW_EXACT_TASK_ATTEMPT,
            self._classifier,
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
            result = _prior_result(failure, attempt, self._classifier)
            if not _needs_prior(result[1]):
                return result
        return None


def _classified_result(
    failure: AirflowFailure,
    log: str,
    source: EvidenceSource,
    classifier: ClassificationAgent,
) -> tuple[AirflowFailure, FailureDiagnosis]:
    """Classify a full log and retain only bounded diagnostic evidence."""
    summary = summarize_task_log(log)
    diagnosis = classifier.classify(failure, log, source)
    hydrated = replace(failure, log=summary.excerpt)
    return hydrated, replace(diagnosis, status=summary.status)


def _prior_result(
    failure: AirflowFailure,
    attempt: PriorTaskLog,
    classifier: ClassificationAgent,
) -> tuple[AirflowFailure, FailureDiagnosis]:
    """Classify one prior same-task attempt and attach its provenance."""
    hydrated, diagnosis = _classified_result(
        failure,
        attempt.log,
        EvidenceSource.AIRFLOW_PRIOR_SAME_TASK,
        classifier,
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
    return diagnosis.kind in {
        FailureKind.UNKNOWN,
        FailureKind.UNKNOWN_RESOURCE_TERMINATION,
        FailureKind.PROBABLE_OOM,
    } or diagnosis.status in {
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
