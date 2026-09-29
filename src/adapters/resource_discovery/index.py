"""Local JSON index and API fallback for Resource Discovery."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Mapping
from pathlib import Path

from workspaces.data_engineering.agents.resource_discovery import (
    ClientLookupIndex,
    ResourceDiscoveryBatchSource,
    ResourceDiscoverySource,
    ResourceIdentifier,
    ResourceRecord,
)

CLIENT_LOOKUP_ENV = "RESOURCE_DISCOVERY_CLIENT_LOOKUP"
DEFAULT_CLIENT_LOOKUP = (
    Path(__file__).resolve().parents[3]
    / ".codex"
    / "skills"
    / "resource-discovery"
    / "references"
    / "client-guuid-lookup.json"
)


class ClientLookupIndexError(ValueError):
    """Raised when a local client lookup cannot be loaded safely."""

    @classmethod
    def unreadable(cls, path: Path, error: Exception) -> ClientLookupIndexError:
        """Create an error for an unreadable or invalid JSON lookup."""
        return cls(f"unable to load client lookup {path}: {error}")

    @classmethod
    def object_required(cls, path: Path) -> ClientLookupIndexError:
        """Create an error for a non-object lookup payload."""
        return cls(f"{path}: expected a JSON object")


class JsonClientLookupSource:
    """Read an immutable non-secret client lookup from JSON."""

    def __init__(self, path: Path = DEFAULT_CLIENT_LOOKUP) -> None:
        """Load and index one explicit lookup file."""
        self.path = path
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ClientLookupIndexError.unreadable(path, error) from error
        if not isinstance(payload, Mapping):
            raise ClientLookupIndexError.object_required(path)
        self.index = ClientLookupIndex.from_mapping(payload)

    async def lookup(
        self,
        identifier: ResourceIdentifier,
    ) -> tuple[ResourceRecord, ...]:
        """Return indexed records without network access."""
        return self.index.lookup(identifier)

    async def alias_candidates(self, alias: str) -> tuple[ResourceRecord, ...]:
        """Return deterministic acronym candidates from the local index."""
        return self.index.alias_candidates(alias)


class IndexedResourceDiscoverySource:
    """Short-circuit unique local identities before querying the live API."""

    def __init__(
        self,
        primary: ResourceDiscoverySource,
        fallback: JsonClientLookupSource,
    ) -> None:
        """Compose the live API with a non-secret local identity index."""
        self.primary = primary
        self.fallback = fallback

    async def lookup(
        self,
        identifier: ResourceIdentifier,
    ) -> tuple[ResourceRecord, ...]:
        """Return a unique local result or query the live provider."""
        indexed = await self.fallback.lookup(identifier)
        if len(indexed) == 1:
            return indexed
        records = await self.primary.lookup(identifier)
        return records or indexed

    async def lookup_batch(
        self,
        identifiers: tuple[ResourceIdentifier, ...],
    ) -> tuple[tuple[ResourceRecord, ...], ...]:
        """Resolve local matches and batch only unresolved identifiers."""
        indexed = tuple(
            self.fallback.index.lookup(identifier) for identifier in identifiers
        )
        unresolved = tuple(
            (index, identifier)
            for index, (identifier, records) in enumerate(
                zip(identifiers, indexed, strict=True)
            )
            if len(records) != 1
        )
        remote: tuple[tuple[ResourceRecord, ...], ...] = ()
        if unresolved:
            unresolved_identifiers = tuple(item[1] for item in unresolved)
            if isinstance(self.primary, ResourceDiscoveryBatchSource):
                remote = await self.primary.lookup_batch(unresolved_identifiers)
            else:
                remote = tuple(
                    await asyncio.gather(
                        *(
                            self.primary.lookup(identifier)
                            for identifier in unresolved_identifiers
                        )
                    )
                )
        remote_by_index = {
            index: records
            for (index, _), records in zip(unresolved, remote, strict=True)
        }
        return tuple(
            records if len(records) == 1 else remote_by_index.get(index, records)
            for index, records in enumerate(indexed)
        )

    async def alias_candidates(self, alias: str) -> tuple[ResourceRecord, ...]:
        """Return local authoritative candidates without a network request."""
        return await self.fallback.alias_candidates(alias)

    async def lookup_local(
        self,
        identifier: ResourceIdentifier,
    ) -> tuple[ResourceRecord, ...]:
        """Return local exact matches without invoking the live API."""
        return await self.fallback.lookup(identifier)


def configured_client_lookup_path() -> Path:
    """Return the explicit local lookup path for this process."""
    configured = os.environ.get(CLIENT_LOOKUP_ENV)
    return Path(configured).expanduser() if configured else DEFAULT_CLIENT_LOOKUP
