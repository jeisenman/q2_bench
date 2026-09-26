"""Production-support domain values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


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
class FailureDiagnosis:
    """Evidence-based diagnosis for one Airflow failure."""

    failure_id: str
    kind: FailureKind
    confidence: str
    evidence: tuple[str, ...]


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
