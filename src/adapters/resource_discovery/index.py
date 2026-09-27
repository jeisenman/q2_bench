"""Local JSON index and API fallback for Resource Discovery."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

from workspaces.data_engineering.agents.resource_discovery import (
    ClientLookupIndex,
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


class IndexedResourceDiscoverySource:
    """Prefer a unique API result and fall back to the local client index."""

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
        """Return a unique live result or an authoritative indexed fallback."""
        records = await self.primary.lookup(identifier)
        if len(records) == 1:
            return records
        indexed = await self.fallback.lookup(identifier)
        return indexed or records


def configured_client_lookup_path() -> Path:
    """Return the explicit local lookup path for this process."""
    configured = os.environ.get(CLIENT_LOOKUP_ENV)
    return Path(configured).expanduser() if configured else DEFAULT_CLIENT_LOOKUP
