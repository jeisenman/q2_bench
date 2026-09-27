"""Discover and normalize regional Airflow failures."""

from __future__ import annotations

import asyncio
from datetime import datetime

from workspaces.data_engineering.agents.prod_support.models import (
    AirflowFailure,
    Region,
)
from workspaces.data_engineering.agents.prod_support.ports import (
    AirflowFailureSource,
    RegionalAirflowFailureSource,
)


class AirflowCheckConfigurationError(ValueError):
    """Raised when an Airflow check has invalid boundaries."""

    @classmethod
    def invalid_window(cls) -> AirflowCheckConfigurationError:
        """Return an error for an empty or reversed query window."""
        return cls("Airflow check end must be later than its start")

    @classmethod
    def empty_regions(cls) -> AirflowCheckConfigurationError:
        """Return an error when no production region is selected."""
        return cls("Airflow check must include at least one region")

    @classmethod
    def timezone_required(cls) -> AirflowCheckConfigurationError:
        """Return an error when query boundaries lack timezone information."""
        return cls("Airflow check boundaries must be timezone-aware")


class AirflowChecker:
    """Discover failures and enforce the operational window contract."""

    def __init__(
        self,
        source: AirflowFailureSource,
        *,
        regions: tuple[Region, ...] = (Region.US_01, Region.CA_02),
    ) -> None:
        """Initialize with a read-only source and selected regions."""
        if not regions:
            raise AirflowCheckConfigurationError.empty_regions()
        self._source = source
        self._regions = frozenset(regions)

    async def check(
        self,
        failed_since: datetime,
        failed_before: datetime,
        *,
        regions: tuple[Region, ...] | None = None,
    ) -> tuple[AirflowFailure, ...]:
        """Return unique selected-region failures in a half-open time window."""
        if failed_since.tzinfo is None or failed_before.tzinfo is None:
            raise AirflowCheckConfigurationError.timezone_required()
        if failed_before <= failed_since:
            raise AirflowCheckConfigurationError.invalid_window()
        selected = frozenset(regions or tuple(self._regions))
        if not selected:
            raise AirflowCheckConfigurationError.empty_regions()
        if isinstance(self._source, RegionalAirflowFailureSource):
            batches = await asyncio.gather(
                *(
                    self._source.discover_region_failures(region, failed_since)
                    for region in sorted(selected, key=lambda item: item.value)
                )
            )
            candidates = tuple(item for batch in batches for item in batch)
        else:
            candidates = await self._source.discover_failures(failed_since)
        return _unique_failures(
            tuple(
                failure
                for failure in candidates
                if failure.region in selected
                and failed_since <= failure.end_at < failed_before
            )
        )


def _unique_failures(
    failures: tuple[AirflowFailure, ...],
) -> tuple[AirflowFailure, ...]:
    """Deduplicate and deterministically order discovered task instances."""
    by_id = {failure.failure_id: failure for failure in failures}
    return tuple(
        sorted(
            by_id.values(),
            key=lambda item: (
                item.region.value,
                item.end_at,
                item.dag_id,
                item.task_id,
                item.run_id,
            ),
        )
    )
