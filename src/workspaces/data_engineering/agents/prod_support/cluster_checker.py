"""Coordinate read-only production cluster health checks."""

from __future__ import annotations

import asyncio

from workspaces.data_engineering.agents.prod_support.cluster_health import (
    RegionalClusterHealth,
)
from workspaces.data_engineering.agents.prod_support.models import Region
from workspaces.data_engineering.agents.prod_support.ports import (
    ClusterHealthSource,
)


class ClusterChecker:
    """Inspect both production regions concurrently."""

    def __init__(self, source: ClusterHealthSource | None = None) -> None:
        """Initialize with an optional read-only cluster-health source."""
        self._source = source

    async def check(self) -> tuple[RegionalClusterHealth, ...]:
        """Return complete US and CA observations or explicit evidence gaps."""
        regions = (Region.US_01, Region.CA_02)
        if self._source is None:
            return tuple(
                RegionalClusterHealth.unavailable(region) for region in regions
            )
        return tuple(
            await asyncio.gather(
                *(self._source.inspect_health(region) for region in regions)
            )
        )
