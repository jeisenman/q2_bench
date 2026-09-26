"""Classify Airflow logs using explicit production-support evidence."""

from __future__ import annotations

from workspaces.data_engineering.agents.prod_support.models import (
    AirflowFailure,
    EvidenceSource,
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
EXIT_MINUS_NINE_MARKERS = (
    "exit -9",
    "exit code -9",
    "exit status -9",
    "return code -9",
)
EVIDENCE_MARKERS = (
    *DISTINCTNESS_MARKERS,
    *OOM_MARKERS,
    *TIMEOUT_MARKERS,
    *EXIT_MINUS_NINE_MARKERS,
    "SIGKILL",
    "Traceback",
    "Exception",
    "ValueError",
)


def classify_log(
    failure: AirflowFailure,
    log: str,
    *,
    source: EvidenceSource = EvidenceSource.UNKNOWN,
) -> FailureDiagnosis:
    """Classify a log without inferring unsupported causes."""
    normalized_log = log.lower()
    if any(marker in log for marker in DISTINCTNESS_MARKERS):
        kind, confidence = FailureKind.DISTINCTNESS, "confirmed"
    elif any(marker in log for marker in OOM_MARKERS):
        kind, confidence = FailureKind.CONFIRMED_OOM, "confirmed"
    elif any(marker in log for marker in TIMEOUT_MARKERS):
        kind = (
            FailureKind.AIRFLOW_CONFIRMED_TIMEOUT
            if source
            in {
                EvidenceSource.AIRFLOW_EXACT_TASK_ATTEMPT,
                EvidenceSource.AIRFLOW_PRIOR_SAME_TASK,
            }
            else FailureKind.OMS_CONFIRMED_TIMEOUT
        )
        confidence = "confirmed"
    elif any(marker in normalized_log for marker in EXIT_MINUS_NINE_MARKERS):
        kind = FailureKind.UNKNOWN_RESOURCE_TERMINATION
        confidence = "unknown"
    elif "SIGKILL" in log:
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
            source=source,
            original_char_count=len(log),
        )
    return _diagnosis(failure, kind, confidence, log, source)


def _diagnosis(
    failure: AirflowFailure,
    kind: FailureKind,
    confidence: str,
    log: str,
    source: EvidenceSource,
) -> FailureDiagnosis:
    normalized = log.replace("\\n", "\n")
    lines = tuple(line.strip() for line in normalized.splitlines() if line.strip())
    matching = tuple(
        line for line in lines if any(marker in line for marker in EVIDENCE_MARKERS)
    )
    evidence = (matching or lines[-3:])[:3]
    return FailureDiagnosis(
        failure.failure_id,
        kind,
        confidence,
        evidence,
        source=source,
        original_char_count=len(log),
    )
