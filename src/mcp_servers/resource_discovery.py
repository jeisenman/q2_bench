"""Read-only Resource Discovery capability MCP server."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from adapters.local import data_engineering_contx_repository
from adapters.resource_discovery import (
    AzureResourceSource,
    ContxClientResourceResolver,
    ContxMetadataSource,
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


@lru_cache(maxsize=1)
def _contx_resolver() -> ContxClientResourceResolver:
    return ContxClientResourceResolver(
        _source(),
        ContxMetadataSource(data_engineering_contx_repository()),
    )


@lru_cache(maxsize=1)
def _azure_source() -> AzureResourceSource:
    return AzureResourceSource.create()


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


@server.tool(
    name="lookup_contx_resources",
    description=(
        "Resolve one client name to a unique client UUID, then "
        "return effective non-secret resources from the configured Contx "
        "metadata checkout. Filter broadly by all, database, datalake, or "
        "storage, or by one exact Contx resource kind."
    ),
)
async def lookup_contx_resources(
    client_name: str,
    resource_type: str = "all",
    resource_kind: str | None = None,
    environment: str = "production",
) -> dict[str, object]:
    """Resolve a client name and return safe effective Contx resources."""
    records = await _contx_resolver().lookup(
        client_name,
        resource_type=resource_type,
        resource_kind=resource_kind,
        environment=environment,
    )
    serialized = [_record(record) for record in records]
    return {
        "client_name": client_name,
        "environment": environment,
        "resource_type": resource_type,
        "resource_kind": resource_kind,
        "count": len(serialized),
        "records": serialized,
    }


@server.tool(
    name="lookup_azure_resources",
    description=(
        "List read-only Azure resource metadata in ra_preprod, "
        "data_engineering, or production. The tool selects the required "
        "subscription explicitly. When Azure CLI authentication or access is "
        "missing, return an az login prompt for the user instead of querying."
    ),
)
async def lookup_azure_resources(
    target: str,
    name: str | None = None,
    resource_group: str | None = None,
    resource_type: str | None = None,
    max_results: int = 100,
) -> dict[str, object]:
    """Return bounded Azure resources or an actionable login prompt."""
    return await _azure_source().lookup(
        target,
        name=name,
        resource_group=resource_group,
        resource_type=resource_type,
        max_results=max_results,
    )


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
