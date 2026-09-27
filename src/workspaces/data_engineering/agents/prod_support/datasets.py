"""Capture redacted production evidence and replay it for benchmarks."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Protocol

from workspaces.data_engineering.agents.prod_support.models import (
    AirflowFailure,
    Region,
)
from workspaces.data_engineering.agents.prod_support.ports import (
    AirflowFailureSource,
    RegionalAirflowFailureSource,
    TaskLogUnavailableError,
)
from workspaces.data_engineering.agents.prod_support.reporting_config import (
    ProdSupportReportConfig,
)

AUTHORIZATION = re.compile(r"(?i)(authorization\s*[:=]\s*)(?:basic|bearer)\s+\S+")
SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(password|token|secret|api[_-]?key)\s*[:=]\s*\S+"
)
OPERATIONAL_HOUR = 5
MAX_PARALLEL = 5


class CaptureConfigurationError(ValueError):
    """Raised when a production-support capture is configured unsafely."""

    @classmethod
    def empty_regions(cls) -> CaptureConfigurationError:
        """Return an error for an empty regional scope."""
        return cls("capture regions must not be empty")

    @classmethod
    def duplicate_regions(cls) -> CaptureConfigurationError:
        """Return an error for repeated regional scope."""
        return cls("capture regions must not contain duplicates")


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
    regions: tuple[Region, ...] = (Region.US_01, Region.CA_02),
) -> Path:
    """Capture scoped Airflow evidence plus prior-day distractors."""
    if not regions:
        raise CaptureConfigurationError.empty_regions()
    if len(set(regions)) != len(regions):
        raise CaptureConfigurationError.duplicate_regions()
    cutoff = datetime.combine(
        operational_date,
        time(hour=OPERATIONAL_HOUR),
        tzinfo=UTC,
    )
    candidates = await _discover_candidates(
        source,
        cutoff - timedelta(days=1),
        regions,
    )
    scrubber = redactor or DefaultLogRedactor()
    config = ProdSupportReportConfig()
    semaphore = asyncio.Semaphore(MAX_PARALLEL)

    async def collect(failure: AirflowFailure) -> dict[str, Any]:
        group = config.omission_group(failure)
        if config.skips_airflow_triage(failure):
            return _serialize(
                failure,
                "",
                triage_status="omitted",
                log_retrieval="omitted_by_policy",
                omission_code=group.value.upper() if group is not None else None,
            )
        try:
            async with semaphore:
                log = await source.fetch_log(failure)
            retrieval = "exact_task_attempt"
        except TaskLogUnavailableError as error:
            log = str(error)
            retrieval = "unavailable"
        return _serialize(
            failure,
            scrubber.redact(log),
            triage_status="investigated",
            log_retrieval=retrieval,
        )

    records = await asyncio.gather(*(collect(failure) for failure in candidates))
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / "airflow_failures.json"
    target.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "operational_date": operational_date.isoformat(),
                "failed_since": cutoff.isoformat(),
                "regions": [region.value for region in regions],
                "triage_omissions": ["D2P", "MI3"],
                "records": records,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return target


async def _discover_candidates(
    source: AirflowFailureSource,
    since: datetime,
    regions: tuple[Region, ...],
) -> tuple[AirflowFailure, ...]:
    if isinstance(source, RegionalAirflowFailureSource):
        batches = await asyncio.gather(
            *(source.discover_region_failures(region, since) for region in regions)
        )
        candidates = tuple(item for batch in batches for item in batch)
    else:
        candidates = tuple(
            failure
            for failure in await source.discover_failures(since)
            if failure.region in regions
        )
    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.region.value,
                item.end_at,
                item.dag_id,
                item.run_id,
                item.task_id,
                item.try_number,
            ),
        )
    )


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


def _serialize(
    failure: AirflowFailure,
    log: str,
    *,
    triage_status: str,
    log_retrieval: str,
    omission_code: str | None = None,
) -> dict[str, Any]:
    value = asdict(failure)
    value["region"] = failure.region.value
    value["start_at"] = failure.start_at.isoformat()
    value["end_at"] = failure.end_at.isoformat()
    value["log"] = log
    value["triage_status"] = triage_status
    value["log_retrieval"] = log_retrieval
    if omission_code is not None:
        value["omission_code"] = omission_code
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
