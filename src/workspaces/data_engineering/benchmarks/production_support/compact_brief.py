"""Produce a bounded, report-ready brief from recorded prod-support evidence."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from .compact_evidence import build_compact_evidence, write_compact_evidence
from .regional_handoff import errors_by_region

UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
OPPORTUNITY_PATTERN = re.compile(
    r"OpportunityId:\s*([0-9a-f-]{36})",
    re.IGNORECASE,
)
WINDOW_START_PATTERN = re.compile(
    r'windowStart\\?":\s*\\?"([^"\\]+)',
    re.IGNORECASE,
)
LARGE_RESEND_THRESHOLD = 100
KPO_ATTEMPT_THRESHOLD = 5


def build_report_brief(
    compact: dict[str, object],
    dataset: Path,
    *,
    resource_discovery: Path | None = None,
    prior_run_logs: Path | None = None,
    prior_context: Path | None = None,
) -> dict[str, object]:
    """Return grouped evidence sufficient for report synthesis."""
    raw = _mapping(json.loads(dataset.read_text(encoding="utf-8")), dataset)
    records = raw.get("records")
    if not isinstance(records, list):
        msg = f"{dataset}: records must be a list"
        raise TypeError(msg)
    compact_records = compact.get("records")
    if not isinstance(compact_records, (list, tuple)):
        msg = "compact records must be a list"
        raise TypeError(msg)
    identities = _identity_lookup(resource_discovery)
    selected = {
        _identity(record) for record in compact_records if isinstance(record, dict)
    }
    groups = _group_records(
        tuple(
            _mapping(record, dataset)
            for record in records
            if _identity(_mapping(record, dataset)) in selected
        ),
        identities,
    )
    brief: dict[str, object] = {
        "summary": compact["summary"],
        "cluster_health": compact.get("cluster_health", []),
        "groups": groups,
        "errors_by_region": errors_by_region(groups),
        "dag_ids_by_region": _dag_ids_by_region(records, selected),
        "instructions": {
            "complete_inventory": True,
            "raw_logs_retained": 0,
            "additional_file_reads_required": False,
        },
    }
    if prior_run_logs is not None:
        brief["prior_run_fallback"] = _prior_run_fallback(prior_run_logs)
    if prior_context is not None:
        brief["prior_context"] = _prior_context(prior_context)
    return brief


def _group_records(
    records: tuple[dict[str, Any], ...],
    identities: dict[str, dict[str, Any]],
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        client_id = _client_id(record)
        key = (str(record["region"]), client_id or "", _job_name(record))
        grouped.setdefault(key, []).append(record)
    return [
        _group_summary(key, values, identities)
        for key, values in sorted(grouped.items())
    ]


def _group_summary(
    key: tuple[str, str, str],
    records: list[dict[str, Any]],
    identities: dict[str, dict[str, Any]],
) -> dict[str, object]:
    region, client_id, job = key
    logs = tuple(str(record.get("log", "")) for record in records)
    identity = identities.get(client_id, {})
    client = _client_label(client_id, identity)
    identity_resolved = _identity_is_resolved(client_id, identity)
    omitted = all(record.get("triage_status") == "omitted" for record in records)
    verified_recovery = omitted and all(
        record.get("success_within_window") is True for record in records
    )
    statuses = Counter(
        (
            "legacy_unverified"
            if record.get("triage_status") == "omitted" and not log
            else _log_status(log)
        )
        for record, log in zip(records, logs, strict=True)
    )
    event_ids = {
        match.group(1).casefold()
        for log in logs
        for match in OPPORTUNITY_PATTERN.finditer(log)
    }
    route = identity.get("reviewed_production_resend_url")
    action_date = _action_date(records, logs)
    resend_supported = (
        job == "validate_event_bus_opportunities"
        and bool(event_ids)
        and isinstance(route, str)
        and bool(route)
    )
    result: dict[str, object] = {
        "region": region,
        "client": client,
        "job": job,
        "record_count": len(records),
        "log_status_counts": dict(sorted(statuses.items())),
        "root_cause": (
            "recovered in-window after exact failure-log review"
            if verified_recovery
            else "legacy omission lacks captured exact-log verification"
            if omitted
            else _root_cause(logs)
        ),
        "identity_resolution_required": bool(client_id) and not identity_resolved,
    }
    if omitted:
        result["success_within_window"] = verified_recovery
    omission_code = _omission_code(records)
    if omission_code is not None:
        result["omission_code"] = omission_code
    if event_ids:
        result["event_count"] = len(event_ids)
        result["action_date"] = action_date
    if resend_supported:
        result["resend_url"] = route
        result["resend_supported"] = True
    if len(event_ids) > LARGE_RESEND_THRESHOLD:
        result["large_resend"] = True
    max_attempt = max(int(record.get("try_number", 1)) for record in records)
    if max_attempt > KPO_ATTEMPT_THRESHOLD:
        result["max_attempt"] = max_attempt
    return result


def _identity_is_resolved(
    client_id: str,
    identity: dict[str, Any],
) -> bool:
    """Return whether a client has a reviewed unique name."""
    return bool(
        client_id
        and identity.get("client_name")
        and str(identity.get("match", "")) in {"unique", "user_confirmed", "reviewed"}
    )


def _dag_ids_by_region(
    records: list[object],
    selected: set[tuple[str, str, str, str, int]],
) -> dict[str, list[str]]:
    grouped: dict[str, set[str]] = {}
    for raw in records:
        record = _mapping(raw, Path("<dataset-record>"))
        if _identity(record) not in selected:
            continue
        grouped.setdefault(str(record["region"]), set()).add(str(record["dag_id"]))
    return {region: sorted(dag_ids) for region, dag_ids in sorted(grouped.items())}


def _identity_lookup(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    raw = _mapping(json.loads(path.read_text(encoding="utf-8")), path)
    lookups = raw.get("lookups")
    if not isinstance(lookups, list):
        msg = f"{path}: lookups must be a list"
        raise TypeError(msg)
    return {
        str(item["client_id"]).casefold(): _mapping(item, path)
        for item in lookups
        if isinstance(item, dict) and item.get("client_id")
    }


def _client_id(record: dict[str, Any]) -> str | None:
    values = f"{record.get('dag_id', '')} {record.get('task_id', '')}"
    match = UUID_PATTERN.search(values)
    return match.group(0).casefold() if match else None


def _client_label(client_id: str, identity: dict[str, Any]) -> str:
    if not client_id:
        return "Regional workload"
    name = identity.get("client_name")
    match = str(identity.get("match", ""))
    if name and match in {"unique", "user_confirmed"}:
        return f"{name} ({client_id[:3]})"
    return f"Unresolved client ({client_id[:3]})"


def _job_name(record: dict[str, Any]) -> str:
    task_id = str(record["task_id"])
    if "client_specific_mi_3_raw_output_validation" in task_id:
        return "MI3 raw-output validation"
    if task_id == "check_for_subscriber_client_errors":
        return "subscriber checks"
    return task_id.split(".", maxsplit=1)[0]


def _omission_code(records: list[dict[str, Any]]) -> str | None:
    text = " ".join(
        f"{record.get('dag_id', '')} {record.get('task_id', '')}".casefold()
        for record in records
    )
    patterns = (
        ("delivery_to_promise", "D2P"),
        ("market_insights_3", "MI3"),
        ("mi_3", "MI3"),
        ("subscriber", "Subscriber"),
        ("log_cleanup", "Maintenance"),
        ("expire_logs", "Maintenance"),
        ("backfill", "Backfill"),
        ("credit_migration_matrix", "CMM"),
    )
    return next((code for pattern, code in patterns if pattern in text), None)


def _root_cause(logs: tuple[str, ...]) -> str:
    text = "\n".join(logs).casefold()
    causes = (
        ("airflowtasktimeout", "Airflow task timeout"),
        ("oomkilled", "OOMKilled"),
        ("outofmemoryerror", "out-of-memory failure"),
        ("missing opportunity snapshot", "missing opportunity snapshots"),
        ("fetchfailedexception", "Spark shuffle FetchFailedException"),
        ("parsererror", "parser error"),
        ("distinctness", "distinctness validation failure"),
        ("dependencies not met", "unmet task dependencies"),
        ("task is not able to be run", "unmet task dependencies"),
        ("http 404", "exact task-attempt log unavailable (HTTP 404)"),
        ("traceback", "terminal traceback retained without a specific root cause"),
    )
    return next(
        (description for marker, description in causes if marker in text),
        "terminal evidence retained without a specific root cause",
    )


def _log_status(log: str) -> str:
    lowered = log.casefold()
    if "http 404" in lowered or "log unavailable" in lowered:
        return "unavailable"
    if "truncated" in lowered:
        return "truncated"
    return "terminal"


def _action_date(
    records: list[dict[str, Any]],
    logs: tuple[str, ...],
) -> str | None:
    for log in logs:
        match = WINDOW_START_PATTERN.search(log)
        if match:
            return match.group(1).partition("T")[0]
    run_id = str(records[0].get("run_id", ""))
    match = re.search(r"(\d{4}-\d{2}-\d{2})T", run_id)
    return match.group(1) if match else None


def _prior_run_fallback(path: Path) -> dict[str, object]:
    raw = _mapping(json.loads(path.read_text(encoding="utf-8")), path)
    runs = raw.get("runs")
    if not isinstance(runs, list):
        msg = f"{path}: runs must be a list"
        raise TypeError(msg)
    first_terminal = next(
        (
            _mapping(run, path)
            for run in runs
            if isinstance(run, dict)
            and run.get("log_status") == "available"
            and str(run.get("state")) == "failed"
        ),
        None,
    )
    return {
        "region": raw.get("region"),
        "dag_id": raw.get("dag_id"),
        "task_id": raw.get("task_id"),
        "latest_status": _mapping(runs[0], path).get("log_status") if runs else None,
        "prior_terminal_run_id": (
            first_terminal.get("run_id") if first_terminal is not None else None
        ),
        "root_cause": (
            _root_cause((str(first_terminal.get("log", "")),))
            if first_terminal is not None
            else None
        ),
    }


def _prior_context(path: Path) -> dict[str, object]:
    raw = _mapping(json.loads(path.read_text(encoding="utf-8")), path)
    failure = _mapping(raw.get("failure", {}), path)
    oms = _mapping(raw.get("oms_evidence", {}), path)
    return {
        "evidence_type": raw.get("evidence_type"),
        "source_operational_date": raw.get("source_operational_date"),
        "current_operational_date": raw.get("current_operational_date"),
        "client_id": _client_id(failure),
        "task_id": failure.get("task_id"),
        "airflow_evidence": raw.get("airflow_evidence", []),
        "oms_corroborating_memory_signal": oms.get("corroborating_memory_signal"),
        "in_current_window": False,
    }


def _identity(record: dict[str, Any]) -> tuple[str, str, str, str, int]:
    return (
        str(record["region"]),
        str(record["dag_id"]),
        str(record["run_id"]),
        str(record["task_id"]),
        int(record.get("try_number", 1)),
    )


def _mapping(raw: object, path: Path) -> dict[str, Any]:
    if not isinstance(raw, dict):
        msg = f"{path}: expected an object"
        raise TypeError(msg)
    return raw


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        msg = "timestamp must include a timezone"
        raise ValueError(msg)
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--cluster-health", type=Path)
    parser.add_argument("--resource-discovery", type=Path)
    parser.add_argument("--prior-run-logs", type=Path)
    parser.add_argument("--prior-context", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    """Write exact records and print one bounded report-ready brief."""
    arguments = _parser().parse_args()
    compact = build_compact_evidence(
        arguments.dataset,
        _timestamp(arguments.start),
        _timestamp(arguments.end),
        cluster_health=arguments.cluster_health,
    )
    write_compact_evidence(compact, arguments.output)
    brief = build_report_brief(
        compact,
        arguments.dataset,
        resource_discovery=arguments.resource_discovery,
        prior_run_logs=arguments.prior_run_logs,
        prior_context=arguments.prior_context,
    )
    sys.stdout.write(f"{json.dumps(brief, separators=(',', ':'), sort_keys=True)}\n")


if __name__ == "__main__":
    main()
