"""Provider-neutral source interfaces for resource discovery."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from workspaces.data_engineering.agents.resource_discovery.models import (
    ResourceIdentifier,
)

ResourceRecord = Mapping[str, object]


class ResourceDiscoverySource(Protocol):
    """Read-only provider boundary for non-secret resource metadata."""

    async def lookup(
        self, identifier: ResourceIdentifier
    ) -> tuple[ResourceRecord, ...]:
        """Return all raw records matching the identifier."""
        ...
