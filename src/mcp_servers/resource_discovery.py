"""Read-only Resource Discovery capability MCP server."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from functools import lru_cache

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
    configure_telemetry(default_service_name=SERVER_NAME)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
