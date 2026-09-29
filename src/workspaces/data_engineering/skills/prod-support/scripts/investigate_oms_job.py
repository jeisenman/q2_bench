#!/usr/bin/env python3
"""Classify OOM and timeout signals for one exact production OMS job."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from oms import (
    REGIONS,
    collect_message_text,
    default_timespan,
    escape_kusto,
    query,
)

CONFIRMED_OOM = re.compile(
    r"\bOOMKilled\b|\bOutOfMemoryError\b|\bout of memory\b",
    re.IGNORECASE,
)
MEMORY_PRESSURE = re.compile(
    r"\bmemory pressure\b|\bmemory limit\b|\bmemory usage\b",
    re.IGNORECASE,
)
SIGKILL = re.compile(
    r"\bSIGKILL\b|(?:exit|return)(?:ed)?(?: with)?(?: code)?\s*:?\s*-9\b",
    re.IGNORECASE,
)
TIMEOUT = re.compile(
    r"\*\*TimeoutError:|\bErrorTimeout\b|\bAirflowTaskTimeout\b|"
    r"\bexecution_timeout\b|\btimed out\b|\btimeout\b",
    re.IGNORECASE,
)


def kusto_query(client_id: str, task_id: str, run_id: str) -> str:
    """Build a client-scoped query for resource and timeout signals."""
    client_id = escape_kusto(client_id)
    task_id = escape_kusto(task_id)
    run_id = escape_kusto(run_id)
    return f"""DI_Scheduling_CL
| where client_id_g == '{client_id}'
| where task_id_s == '{task_id}'
| where run_id_s == '{run_id}'
| where Message has_any (
    'OOMKilled',
    'OutOfMemoryError',
    'out of memory',
    'memory pressure',
    'memory limit',
    'SIGKILL',
    'exit code -9',
    'return code -9',
    'TimeoutError',
    'ErrorTimeout',
    'AirflowTaskTimeout',
    'execution_timeout',
    'timed out',
    'timeout'
  )
| project TimeGenerated, Message
| order by TimeGenerated asc"""


def read_log_file(path: str) -> str:
    return sys.stdin.read() if path == "-" else Path(path).read_text()


def evidence_lines(text: str) -> list[str]:
    """Return unique signal-bearing lines in source order."""
    evidence: list[str] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line in seen:
            continue
        if (
            CONFIRMED_OOM.search(line)
            or MEMORY_PRESSURE.search(line)
            or SIGKILL.search(line)
            or TIMEOUT.search(line)
        ):
            seen.add(line)
            evidence.append(line)
    return evidence


def classify(text: str) -> tuple[str, str]:
    """Return classification and confidence from explicit OMS evidence."""
    if CONFIRMED_OOM.search(text):
        return "confirmed_oom", "confirmed"
    if TIMEOUT.search(text):
        return "timeout", "confirmed"
    if SIGKILL.search(text) and MEMORY_PRESSURE.search(text):
        return "probable_oom", "probable"
    if SIGKILL.search(text):
        return "unknown_resource_termination", "unknown"
    return "unknown", "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", required=True, choices=REGIONS)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--dag-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--start-utc")
    parser.add_argument("--end-utc")
    parser.add_argument(
        "--log-file",
        help="Parse a captured log instead of querying OMS; use - for stdin.",
    )
    args = parser.parse_args()

    if args.log_file:
        log_text = read_log_file(args.log_file)
    else:
        start, end = default_timespan(args.start_utc, args.end_utc)
        try:
            log_text = collect_message_text(
                query(
                    args.region,
                    kusto_query(args.client_id, args.task_id, args.run_id),
                    start,
                    end,
                )
            )
        except RuntimeError as error:
            print(f"Unable to investigate OMS job: {error}", file=sys.stderr)
            return 1

    classification, confidence = classify(log_text)
    result = {
        "region": args.region,
        "client_id": args.client_id,
        "dag_id": args.dag_id,
        "run_id": args.run_id,
        "task_id": args.task_id,
        "classification": classification,
        "confidence": confidence,
        "evidence": evidence_lines(log_text),
        "distinctness_checks": [],
        "recoverable_opportunity_ids": [],
        "non_recoverable_opportunity_ids": [],
        "rerun_targets": [],
        "mutation_performed": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
