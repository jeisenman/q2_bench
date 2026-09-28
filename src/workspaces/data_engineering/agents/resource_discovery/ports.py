"""Provider-neutral source interfaces for resource discovery."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

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


@runtime_checkable
class ResourceAliasCandidateSource(Protocol):
    """Find deterministic canonical candidates for an unconfirmed alias."""

    async def alias_candidates(self, alias: str) -> tuple[ResourceRecord, ...]:
        """Return authoritative records whose generated acronym matches."""
        ...


@runtime_checkable
class ResourceLocalLookupSource(Protocol):
    """Expose a network-free authoritative lookup tier."""

    async def lookup_local(
        self,
        identifier: ResourceIdentifier,
    ) -> tuple[ResourceRecord, ...]:
        """Return exact local records without invoking a remote provider."""
        ...
