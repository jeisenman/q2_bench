"""Classify Airflow logs using explicit production-support evidence."""

from __future__ import annotations

from workspaces.data_engineering.agents.prod_support.models import (
    AirflowFailure,
    FailureDiagnosis,
    FailureKind,
)

DISTINCTNESS_MARKERS = (
    "Distinctness validation failed",
    "Validate distinctness - counts",
)
OOM_MARKERS = ("OOMKilled", "OutOfMemoryError")
TIMEOUT_MARKERS = (
    "**TimeoutError",
    "ErrorTimeout",
    "AirflowTaskTimeout",
    "execution_timeout",
)
MEMORY_PRESSURE_MARKERS = ("memory pressure", "memory limit")
EVIDENCE_MARKERS = (
    *DISTINCTNESS_MARKERS,
    *OOM_MARKERS,
    *TIMEOUT_MARKERS,
    "exit -9",
    "SIGKILL",
    "Traceback",
    "Exception",
    "ValueError",
)


def classify_log(failure: AirflowFailure, log: str) -> FailureDiagnosis:
    """Classify a log without inferring unsupported causes."""
    if any(marker in log for marker in DISTINCTNESS_MARKERS):
        kind, confidence = FailureKind.DISTINCTNESS, "confirmed"
    elif any(marker in log for marker in OOM_MARKERS):
        kind, confidence = FailureKind.CONFIRMED_OOM, "confirmed"
    elif any(marker in log for marker in TIMEOUT_MARKERS):
        kind, confidence = FailureKind.OMS_CONFIRMED_TIMEOUT, "confirmed"
    elif "exit -9" in log or "SIGKILL" in log:
        if any(marker in log.lower() for marker in MEMORY_PRESSURE_MARKERS):
            kind, confidence = FailureKind.PROBABLE_OOM, "probable"
        else:
            kind = FailureKind.UNKNOWN_RESOURCE_TERMINATION
            confidence = "unknown"
    elif "Traceback" in log or "Exception" in log:
        kind, confidence = FailureKind.APPLICATION_ERROR, "confirmed"
    else:
        return FailureDiagnosis(
            failure_id=failure.failure_id,
            kind=FailureKind.UNKNOWN,
            confidence="unknown",
            evidence=(),
        )
    return _diagnosis(failure, kind, confidence, log)


def _diagnosis(
    failure: AirflowFailure,
    kind: FailureKind,
    confidence: str,
    log: str,
) -> FailureDiagnosis:
    normalized = log.replace("\\n", "\n")
    lines = tuple(line.strip() for line in normalized.splitlines() if line.strip())
    matching = tuple(
        line for line in lines if any(marker in line for marker in EVIDENCE_MARKERS)
    )
    evidence = (matching or lines[-3:])[:3]
    return FailureDiagnosis(failure.failure_id, kind, confidence, evidence)
