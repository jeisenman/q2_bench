"""Read-only Resource Discovery capability MCP server."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from adapters.resource_discovery import (
    IndexedResourceDiscoverySource,
    JsonClientLookupSource,
    ResourceDiscoveryApiSource,
    configured_client_lookup_path,
)
from adapters.telemetry import configure_telemetry
from workspaces.data_engineering.agents.resource_discovery import (
    IdentifierKind,
    ResourceIdentifier,
    ResourceRecord,
)

SERVER_NAME = "resource-discovery-capabilities"
MIN_QUOTED_VALUE_LENGTH = 2
server = MCPServer(
    SERVER_NAME,
    description="Read-only non-secret Resource Discovery capabilities.",
)


@lru_cache(maxsize=1)
def _source() -> IndexedResourceDiscoverySource:
    return IndexedResourceDiscoverySource(
        ResourceDiscoveryApiSource.from_environment(),
        JsonClientLookupSource(configured_client_lookup_path()),
    )


@server.tool(
    name="lookup_resources",
    description=(
        "Return every allowlisted Resource Discovery match for one complete "
        "identifier without choosing among ambiguous records."
    ),
)
async def lookup_resources(
    identifier_kind: str,
    identifier_value: str,
) -> dict[str, object]:
    """Return zero, one, or multiple non-secret records."""
    identifier = ResourceIdentifier(
        IdentifierKind(identifier_kind),
        identifier_value,
    )
    records = await _source().lookup(identifier)
    serialized = [_record(record) for record in records]
    return {
        "identifier_kind": identifier.kind.value,
        "identifier_value": identifier.value,
        "count": len(serialized),
        "records": serialized,
    }


@server.tool(
    name="lookup_resources_batch",
    description=(
        "Return Resource Discovery matches for several complete identifiers in "
        "one read-only capability call."
    ),
)
async def lookup_resources_batch(
    identifiers: list[Mapping[str, str]],
) -> dict[str, object]:
    """Return ordered Resource Discovery results for a batch of identifiers."""
    parsed = tuple(
        ResourceIdentifier(
            IdentifierKind(item["identifier_kind"]),
            item["identifier_value"],
        )
        for item in identifiers
    )
    records = tuple(
        await asyncio.gather(*(_source().lookup(identifier) for identifier in parsed))
    )
    return {
        "count": len(records),
        "results": [
            {
                "identifier_kind": identifier.kind.value,
                "identifier_value": identifier.value,
                "count": len(identifier_records),
                "records": [_record(record) for record in identifier_records],
            }
            for identifier, identifier_records in zip(parsed, records, strict=True)
        ],
    }


def _record(record: ResourceRecord) -> dict[str, object]:
    """Copy an allowlisted record into a JSON-compatible object."""
    return {
        name: value
        for name, value in record.items()
        if isinstance(value, str | int | float | bool) or value is None
    }


def main() -> None:
    """Run the read-only Resource Discovery MCP server over stdio."""
    configure_environment()
    configure_telemetry(default_service_name=SERVER_NAME)
    server.run(transport="stdio")


def configure_environment(env_file: Path = Path(".env")) -> None:
    """Load local credentials without replacing exported environment values."""
    if not env_file.is_file():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if (
            len(value) >= MIN_QUOTED_VALUE_LENGTH
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]
        os.environ[key] = value


if __name__ == "__main__":
    main()
