"""Build bounded production-support evidence from recorded benchmark inputs."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

MAX_EVIDENCE_LINES = 3
MAX_EVIDENCE_LINE_CHARACTERS = 240
TERMINAL_MARKERS = (
    "airflowtasktimeout",
    "distinctness",
    "exception",
    "exit -9",
    "exit code -9",
    "failed",
    "missing opportunity",
    "oomkilled",
    "outofmemoryerror",
    "parsererror",
    "return code",
    "sigkill",
    "task is not able to be run",
    "traceback",
    "unique events",
)
TRUNCATION_MARKERS = ("log truncated", "truncated log", "was not found in the log")
UNAVAILABLE_MARKERS = ("http 404", "status code 404", "log unavailable")


class CompactEvidenceError(ValueError):
    """Raised when recorded benchmark evidence is malformed."""

    @classmethod
    def invalid_window(cls) -> CompactEvidenceError:
        """Return an error for a reversed or empty window."""
        return cls("end_at must be after start_at")

    @classmethod
    def list_required(cls, path: Path, field: str) -> CompactEvidenceError:
        """Return an error for a required list field."""
        return cls(f"{path}: {field} must be a list")

    @classmethod
    def object_required(cls, path: Path) -> CompactEvidenceError:
        """Return an error for a required mapping."""
        return cls(f"{path}: expected an object")

    @classmethod
    def invalid_timestamp(cls, field: str) -> CompactEvidenceError:
        """Return an error for a malformed timestamp."""
        return cls(f"{field} must be ISO-8601")

    @classmethod
    def timezone_required(cls, field: str) -> CompactEvidenceError:
        """Return an error for a timestamp without an offset."""
        return cls(f"{field} must include a timezone")


def build_compact_evidence(
    dataset: Path,
    start_at: datetime,
    end_at: datetime,
    *,
    cluster_health: Path | None = None,
) -> dict[str, object]:
    """Return bounded exact-attempt records and normalized cluster health."""
    if end_at <= start_at:
        raise CompactEvidenceError.invalid_window()
    raw = _mapping(json.loads(dataset.read_text(encoding="utf-8")), dataset)
    records = raw.get("records")
    if not isinstance(records, list):
        raise CompactEvidenceError.list_required(dataset, "records")
    compact = tuple(
        _compact_record(record)
        for record in records
        if _inside_window(record, start_at, end_at)
    )
    regions = Counter(str(record["region"]) for record in compact)
    omitted_count = sum(record.get("triage_status") == "omitted" for record in compact)
    exact_log_count = sum(
        record.get("log_retrieval") != "omitted_by_policy" for record in compact
    )
    result: dict[str, object] = {
        "schema_version": 1,
        "dataset": str(dataset),
        "window": {
            "start": start_at.isoformat(),
            "end": end_at.isoformat(),
        },
        "summary": {
            "record_count": len(compact),
            "regions": dict(sorted(regions.items())),
            "exact_log_records": exact_log_count,
            "triage_omitted_records": omitted_count,
            "raw_logs_retained": 0,
        },
        "records": compact,
    }
    if cluster_health is not None:
        result["cluster_health"] = _compact_cluster_health(cluster_health)
    return result


def write_compact_evidence(result: dict[str, object], output: Path) -> None:
    """Write deterministic compact evidence without printing raw log bodies."""
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def summary_record(
    result: dict[str, object],
    output: Path | None = None,
) -> dict[str, object]:
    """Return the small command result intended for the execution trace."""
    summary = _mapping(result["summary"], Path("<generated>"))
    value: dict[str, object] = {
        "compact_evidence": str(output) if output is not None else "stdout",
        **summary,
    }
    cluster = result.get("cluster_health")
    if isinstance(cluster, list):
        value["cluster_regions"] = {
            str(item["region"]): str(item["state"])
            for item in cluster
            if isinstance(item, dict)
        }
    return value


def _compact_record(raw: object) -> dict[str, object]:
    record = _mapping(raw, Path("<dataset-record>"))
    triage_status = str(record.get("triage_status", "investigated"))
    log = str(record.get("log", ""))
    if triage_status == "omitted" and not log:
        result: dict[str, object] = {
            "region": str(record["region"]),
            "dag_id": str(record["dag_id"]),
            "run_id": str(record["run_id"]),
            "task_id": str(record["task_id"]),
            "try_number": int(record.get("try_number", 1)),
            "triage_status": triage_status,
            "log_retrieval": "omitted_by_policy",
            "log_status": "omitted",
            "log_characters": 0,
            "evidence": (),
            "success_within_window": record.get("success_within_window"),
            "verification_status": "legacy_unverified",
        }
        omission_code = record.get("omission_code")
        if omission_code is not None:
            result["omission_code"] = str(omission_code)
        return result
    evidence = _evidence_lines(log)
    result = {
        "region": str(record["region"]),
        "dag_id": str(record["dag_id"]),
        "run_id": str(record["run_id"]),
        "task_id": str(record["task_id"]),
        "try_number": int(record.get("try_number", 1)),
        "triage_status": triage_status,
        "log_retrieval": str(record.get("log_retrieval", "exact_replay_task_attempt")),
        "log_status": _log_status(log, evidence),
        "log_characters": len(log),
        "evidence": evidence,
    }
    if "success_within_window" in record:
        result["success_within_window"] = bool(record["success_within_window"])
    omission_code = record.get("omission_code")
    if omission_code is not None:
        result["omission_code"] = str(omission_code)
    return result


def _inside_window(
    raw: object,
    start_at: datetime,
    end_at: datetime,
) -> bool:
    record = _mapping(raw, Path("<dataset-record>"))
    ended_at = _timestamp(str(record["end_at"]), "record end_at")
    return start_at <= ended_at < end_at


def _evidence_lines(log: str) -> tuple[str, ...]:
    normalized = log.replace("\\n", "\n")
    lines = tuple(line.strip() for line in normalized.splitlines() if line.strip())
    relevant = tuple(
        line
        for line in lines
        if any(marker in line.casefold() for marker in TERMINAL_MARKERS)
    )
    selected = relevant[:MAX_EVIDENCE_LINES] or lines[-MAX_EVIDENCE_LINES:]
    return tuple(line[:MAX_EVIDENCE_LINE_CHARACTERS] for line in selected)


def _log_status(log: str, evidence: tuple[str, ...]) -> str:
    lowered = log.casefold()
    if any(marker in lowered for marker in UNAVAILABLE_MARKERS):
        return "unavailable"
    if any(marker in lowered for marker in TRUNCATION_MARKERS):
        return "truncated"
    if evidence and any(
        marker in line.casefold() for line in evidence for marker in TERMINAL_MARKERS
    ):
        return "terminal"
    return "non_diagnostic"


def _compact_cluster_health(path: Path) -> list[dict[str, object]]:
    raw = _mapping(json.loads(path.read_text(encoding="utf-8")), path)
    captured_at = str(raw.get("captured_at", "unknown"))
    regions = raw.get("regions")
    if not isinstance(regions, list):
        raise CompactEvidenceError.list_required(path, "regions")
    return [_cluster_region(item, captured_at) for item in regions]


def _cluster_region(raw: object, captured_at: str) -> dict[str, object]:
    region = _mapping(raw, Path("<cluster-region>"))
    if "pods_healthy" in region:
        warnings = tuple(str(value) for value in region.get("warnings", ()))
        symptoms = tuple(str(value) for value in region.get("symptoms", ()))
        return {
            "region": str(region["region"]),
            "observed_at": str(region.get("observed_at") or captured_at),
            "state": str(region.get("state", "unknown")),
            "application_healthy": region.get("application_healthy"),
            "pods_healthy": region.get("pods_healthy"),
            "dags_parsing_healthy": region.get("dags_parsing_healthy"),
            "active_dag_count": region.get("active_dag_count"),
            "restart_count": region.get("restart_count"),
            "cumulative_restart_count": region.get("cumulative_restart_count"),
            "restart_window_start": region.get("restart_window_start"),
            "restart_window_end": region.get("restart_window_end"),
            "keda_status": str(region.get("keda_status", "unknown")),
            "symptoms": symptoms,
            "warnings": warnings,
        }
    application = _mapping(
        region.get("application_health", {}),
        Path("<application-health>"),
    )
    pods = _mapping(region.get("pods", {}), Path("<pods>"))
    dags = _mapping(region.get("dags", {}), Path("<dags>"))
    keda = _mapping(region.get("keda_scaledobjects", {}), Path("<keda>"))
    application_healthy = bool(application) and all(
        str(value).casefold() == "healthy" for value in application.values()
    )
    pods_healthy = pods.get("primary_pods_healthy")
    if not isinstance(pods_healthy, bool):
        pods_healthy = int(pods.get("running_unready_count", 0)) == 0
    parsing_healthy = str(dags.get("parsing_status", "")).casefold() == "healthy"
    active_count = int(dags.get("active_count", 0))
    state = (
        "healthy"
        if application_healthy and pods_healthy and parsing_healthy and active_count > 0
        else "unhealthy"
    )
    warnings = tuple(
        str(value)
        for value in (
            pods.get("warning"),
            keda.get("detail") if keda.get("status") != "healthy" else None,
        )
        if value
    )
    return {
        "region": str(region["region"]),
        "observed_at": captured_at,
        "state": state,
        "application_healthy": application_healthy,
        "pods_healthy": pods_healthy,
        "dags_parsing_healthy": parsing_healthy,
        "active_dag_count": active_count,
        "restart_count": int(pods.get("dag_processor_restart_count", 0)),
        "keda_status": str(keda.get("status", "unknown")),
        "warnings": warnings,
    }


def _mapping(raw: object, path: Path) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise CompactEvidenceError.object_required(path)
    return raw


def _timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CompactEvidenceError.invalid_timestamp(field) from error
    if parsed.tzinfo is None:
        raise CompactEvidenceError.timezone_required(field)
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--cluster-health", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    """Run the standalone parser used inside isolated benchmark containers."""
    arguments = _parser().parse_args()
    result = build_compact_evidence(
        arguments.dataset,
        _timestamp(arguments.start, "--start"),
        _timestamp(arguments.end, "--end"),
        cluster_health=arguments.cluster_health,
    )
    write_compact_evidence(result, arguments.output)
    sys.stdout.write(
        f"{json.dumps(summary_record(result, arguments.output), sort_keys=True)}\n"
    )


if __name__ == "__main__":
    main()
