"""Coordinate read-only production cluster health checks."""

from __future__ import annotations

import asyncio
from datetime import datetime

from workspaces.data_engineering.agents.production_support.cluster_health import (
    RegionalClusterHealth,
)
from workspaces.data_engineering.agents.production_support.models import Region
from workspaces.data_engineering.agents.production_support.ports import (
    ClusterHealthSource,
)


class ClusterCheckConfigurationError(ValueError):
    """Raised when a cluster check has no regional scope."""

    @classmethod
    def empty_regions(cls) -> ClusterCheckConfigurationError:
        """Return an error for an empty cluster scope."""
        return cls("cluster check must include at least one region")


class ClusterChecker:
    """Inspect both production regions concurrently."""

    def __init__(self, source: ClusterHealthSource | None = None) -> None:
        """Initialize with an optional read-only cluster-health source."""
        self._source = source

    async def check(
        self,
        regions: tuple[Region, ...] = (Region.US_01, Region.CA_02),
        *,
        restart_window_start: datetime,
        restart_window_end: datetime,
    ) -> tuple[RegionalClusterHealth, ...]:
        """Return selected regional observations or explicit evidence gaps."""
        if not regions:
            raise ClusterCheckConfigurationError.empty_regions()
        if self._source is None:
            return tuple(
                RegionalClusterHealth.unavailable(region) for region in regions
            )
        return tuple(
            await asyncio.gather(
                *(
                    self._source.inspect_health(
                        region,
                        restart_window_start,
                        restart_window_end,
                    )
                    for region in regions
                )
            )
        )
