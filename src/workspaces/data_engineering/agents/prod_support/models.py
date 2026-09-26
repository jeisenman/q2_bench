"""Production-support domain values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from domain import AgentResult


class Region(StrEnum):
    """Supported production Airflow regions."""

    US_01 = "US-01"
    CA_02 = "CA-02"


class FailureKind(StrEnum):
    """Supported evidence-based failure classifications."""

    DISTINCTNESS = "distinctness"
    OMS_CONFIRMED_TIMEOUT = "oms_confirmed_timeout"
    AIRFLOW_CONFIRMED_TIMEOUT = "airflow_confirmed_timeout"
    CONFIRMED_OOM = "confirmed_oom"
    PROBABLE_OOM = "probable_oom"
    UNKNOWN_RESOURCE_TERMINATION = "unknown_resource_termination"
    APPLICATION_ERROR = "application_error"
    UNKNOWN = "unknown"


class EvidenceSource(StrEnum):
    """Read-only source used for one diagnosis."""

    UNKNOWN = "unknown"
    AIRFLOW_EXACT_TASK_ATTEMPT = "airflow_exact_task_attempt"
    AIRFLOW_PRIOR_SAME_TASK = "airflow_prior_same_task"
    OMS_EXACT_JOB = "oms_exact_job"


class EvidenceStatus(StrEnum):
    """Completeness of evidence retrieved for one failed task."""

    UNKNOWN = "unknown"
    TERMINAL = "terminal"
    NON_DIAGNOSTIC = "non_diagnostic"
    TRUNCATED = "truncated"
    UNAVAILABLE = "unavailable"


class PriorTaskLogValueError(ValueError):
    """Raised when prior same-task evidence has invalid identity."""

    @classmethod
    def empty_run_id(cls) -> PriorTaskLogValueError:
        """Return an error for an empty prior run identity."""
        return cls("prior task-log run_id must not be empty")

    @classmethod
    def invalid_try_number(cls) -> PriorTaskLogValueError:
        """Return an error for a non-positive prior attempt."""
        return cls("prior task-log try_number must be positive")


@dataclass(frozen=True, slots=True)
class AirflowFailure:
    """One failed Airflow task instance and its captured evidence."""

    region: Region
    dag_id: str
    run_id: str
    task_id: str
    start_at: datetime
    end_at: datetime
    try_number: int = 1
    log: str = ""

    def __post_init__(self) -> None:
        """Validate required failure metadata."""
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
            message = "Airflow timestamps must be timezone-aware"
            raise ValueError(message)
        if self.end_at < self.start_at:
            message = "Airflow failure end time must not precede start time"
            raise ValueError(message)
        if self.try_number < 1:
            message = "Airflow try number must be positive"
            raise ValueError(message)
        for value, label in (
            (self.dag_id, "dag_id"),
            (self.run_id, "run_id"),
            (self.task_id, "task_id"),
        ):
            if not value.strip():
                message = f"{label} must not be empty"
                raise ValueError(message)

    @property
    def failure_id(self) -> str:
        """Return a stable task-instance identifier."""
        return "|".join((self.region.value, self.dag_id, self.run_id, self.task_id))


@dataclass(frozen=True, slots=True)
class PriorTaskLog:
    """One earlier exact attempt for the same DAG and task."""

    run_id: str
    try_number: int
    log: str

    def __post_init__(self) -> None:
        """Validate prior-attempt identity and evidence."""
        if not self.run_id.strip():
            raise PriorTaskLogValueError.empty_run_id()
        if self.try_number < 1:
            raise PriorTaskLogValueError.invalid_try_number()


@dataclass(frozen=True, slots=True)
class FailureDiagnosis:
    """Evidence-based diagnosis for one Airflow failure."""

    failure_id: str
    kind: FailureKind
    confidence: str
    evidence: tuple[str, ...]
    source: EvidenceSource = EvidenceSource.UNKNOWN
    status: EvidenceStatus = EvidenceStatus.UNKNOWN
    original_char_count: int = 0


@dataclass(frozen=True, slots=True)
class ProdSupportOutcome:
    """Structured result used by benchmark evaluators and report adapters."""

    operational_date: date
    failed_since: datetime
    failures: tuple[AirflowFailure, ...]
    diagnoses: tuple[FailureDiagnosis, ...]
    report: str
    developer_report: str = ""
    data_internal_report: str = ""
    follow_up: str = ""
    resource_discovery_results: tuple[AgentResult, ...] = ()
