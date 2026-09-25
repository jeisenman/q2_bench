"""Capture redacted production evidence and replay it for benchmarks."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Protocol

from agentsdk.ws.data_engineering.agents.prod_support.models import (
    AirflowFailure,
    Region,
)
from agentsdk.ws.data_engineering.agents.prod_support.ports import (
    AirflowFailureSource,
)

AUTHORIZATION = re.compile(r"(?i)(authorization\s*[:=]\s*)(?:basic|bearer)\s+\S+")
SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(password|token|secret|api[_-]?key)\s*[:=]\s*\S+"
)
OPERATIONAL_HOUR = 5


class LogRedactor(Protocol):
    """Redact sensitive content before benchmark persistence."""

    def redact(self, value: str) -> str:
        """Return a safe representation of a captured log."""


class DefaultLogRedactor:
    """Mask common authorization and credential patterns."""

    def redact(self, value: str) -> str:
        """Mask common secret-bearing log fragments."""
        value = AUTHORIZATION.sub(r"\1<redacted>", value)
        return SECRET_ASSIGNMENT.sub(r"\1=<redacted>", value)


async def capture_day(
    source: AirflowFailureSource,
    operational_date: date,
    destination: Path,
    *,
    redactor: LogRedactor | None = None,
) -> Path:
    """Capture one operational day plus prior-day distractor failures."""
    cutoff = datetime.combine(
        operational_date,
        time(hour=OPERATIONAL_HOUR),
        tzinfo=UTC,
    )
    candidates = await source.discover_failures(cutoff - timedelta(days=1))
    scrubber = redactor or DefaultLogRedactor()
    records = []
    for failure in candidates:
        log = failure.log or await source.fetch_log(failure)
        records.append(_serialize(failure, scrubber.redact(log)))
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / "airflow_failures.json"
    target.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "operational_date": operational_date.isoformat(),
                "failed_since": cutoff.isoformat(),
                "records": records,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return target


class ReplayAirflowFailureSource:
    """Replay captured Airflow evidence without production access."""

    def __init__(self, dataset_path: Path) -> None:
        """Load and validate one captured dataset."""
        raw = json.loads(dataset_path.read_text(encoding="utf-8"))
        records = raw.get("records")
        if not isinstance(records, list):
            message = f"{dataset_path}: records must be a list"
            raise TypeError(message)
        self._failures = tuple(_deserialize(item) for item in records)

    async def discover_failures(self, since: datetime) -> tuple[AirflowFailure, ...]:
        """Return all records so the agent's cutoff filtering is testable."""
        del since
        return self._failures

    async def fetch_log(self, failure: AirflowFailure) -> str:
        """Return the captured log embedded in a replay record."""
        return failure.log


def _serialize(failure: AirflowFailure, log: str) -> dict[str, Any]:
    value = asdict(failure)
    value["region"] = failure.region.value
    value["start_at"] = failure.start_at.isoformat()
    value["end_at"] = failure.end_at.isoformat()
    value["log"] = log
    return value


def _deserialize(value: object) -> AirflowFailure:
    if not isinstance(value, dict):
        message = "captured Airflow record must be an object"
        raise TypeError(message)
    return AirflowFailure(
        region=Region(str(value["region"])),
        dag_id=str(value["dag_id"]),
        run_id=str(value["run_id"]),
        task_id=str(value["task_id"]),
        start_at=datetime.fromisoformat(str(value["start_at"])),
        end_at=datetime.fromisoformat(str(value["end_at"])),
        try_number=int(value.get("try_number", 1)),
        log=str(value.get("log", "")),
    )
