"""Translate production-support prompts into Airflow query windows."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

DATE_PATTERN = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})\b")
RUN_START_PATTERN = re.compile(
    r"run/date_start\s+(\d{4}-\d{2}-\d{2})[,\s]+(\d{2}:\d{2}:\d{2})\s+UTC",
    re.IGNORECASE,
)
OPERATIONAL_HOUR = 5
SHORT_YEAR_LIMIT = 100
SHORT_YEAR_BASE = 2000
YESTERDAY_DAYS_BACK = 2


@dataclass(frozen=True, slots=True)
class QueryWindow:
    """Resolved Airflow failure query window."""

    operational_date: date
    failed_since: datetime
    source: str


def resolve_query_window(prompt: str, reference_time: datetime) -> QueryWindow:
    """Resolve explicit and relative prompts using the 05:00 UTC convention."""
    reference = _as_utc(reference_time)
    run_start = RUN_START_PATTERN.search(prompt)
    if run_start:
        failed_since = datetime.fromisoformat(
            f"{run_start.group(1)}T{run_start.group(2)}+00:00"
        )
        return QueryWindow(failed_since.date(), failed_since, "run_date_start")

    explicit = DATE_PATTERN.search(prompt)
    if explicit:
        year = int(explicit.group(3))
        if year < SHORT_YEAR_LIMIT:
            year += SHORT_YEAR_BASE
        requested = date(year, int(explicit.group(1)), int(explicit.group(2)))
        return QueryWindow(requested, _anchor(requested), "explicit_date")

    days_back = YESTERDAY_DAYS_BACK if "yesterday" in prompt.lower() else 1
    operational_date = reference.date() - timedelta(days=days_back)
    source = "yesterday" if days_back == YESTERDAY_DAYS_BACK else "default"
    return QueryWindow(operational_date, _anchor(operational_date), source)


def _anchor(value: date) -> datetime:
    return datetime.combine(value, time(hour=OPERATIONAL_HOUR), tzinfo=UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        message = "reference time must be timezone-aware"
        raise ValueError(message)
    return value.astimezone(UTC)
