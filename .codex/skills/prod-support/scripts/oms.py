"""Shared read-only OMS/Log Analytics query support for production triage."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta

from azure_auth import ensure_azure_login

REGIONS = {
    "us01": {
        "airflow_host": "https://airflow-us01.precisionlender.com",
        "workspace": "6220c6e1-57a3-49c2-901c-bb5e5106f2b0",
    },
    "ca02": {
        "airflow_host": "https://airflow-ca02.precisionlender.com",
        "workspace": "2fc9684b-5d16-42f0-ab99-9dc044e4ea73",
    },
}


def default_timespan(
    start_utc: str | None,
    end_utc: str | None,
) -> tuple[str, str]:
    """Return an explicit UTC query window, defaulting to the prior 24 hours."""
    now = datetime.now(UTC).replace(microsecond=0)
    end = end_utc or now.isoformat().replace("+00:00", "Z")
    start = start_utc or (now - timedelta(hours=24)).isoformat().replace(
        "+00:00",
        "Z",
    )
    return start, end


def escape_kusto(value: str) -> str:
    """Escape a value embedded in a single-quoted Kusto string."""
    return value.replace("'", "''")


def query(
    region: str,
    analytics_query: str,
    start_utc: str,
    end_utc: str,
) -> object:
    """Run one authenticated, read-only Log Analytics query."""
    if region not in REGIONS:
        raise ValueError(f"Unsupported OMS region: {region}")
    if not ensure_azure_login():
        raise RuntimeError("Azure production login is unavailable.")

    command = [
        "az",
        "monitor",
        "log-analytics",
        "query",
        "-w",
        REGIONS[region]["workspace"],
        "--timespan",
        f"{start_utc}/{end_utc}",
        "--analytics-query",
        analytics_query,
        "-o",
        "json",
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Log Analytics query failed.")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("Log Analytics returned invalid JSON.") from error


def collect_message_text(payload: object) -> str:
    """Collect Message fields recursively from an OMS JSON result."""
    messages: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key.lower() in {"message", "message_s"} and isinstance(value, str):
                messages.append(value)
            else:
                nested = collect_message_text(value)
                if nested:
                    messages.extend(nested.splitlines())
    elif isinstance(payload, list):
        for value in payload:
            nested = collect_message_text(value)
            if nested:
                messages.extend(nested.splitlines())
    return "\n".join(messages)
