"""Resource Discovery source backed by a read-only MCP capability."""

from __future__ import annotations

from collections.abc import Mapping

from adapters.mcp.client import McpToolCaller
from workspaces.data_engineering.agents.resource_discovery import (
    ResourceIdentifier,
    ResourceRecord,
)


class ResourceDiscoveryMcpError(RuntimeError):
    """Raised when Resource Discovery MCP data is malformed."""

    @classmethod
    def invalid_records(cls) -> ResourceDiscoveryMcpError:
        """Return an error for a non-list record collection."""
        return cls("Resource Discovery MCP records must be a list of objects")


class ResourceDiscoveryMcpSource:
    """Implement the read-only Resource Discovery source protocol through MCP."""

    def __init__(self, caller: McpToolCaller) -> None:
        """Initialize with an injected MCP caller."""
        self._caller = caller

    async def lookup(
        self,
        identifier: ResourceIdentifier,
    ) -> tuple[ResourceRecord, ...]:
        """Return every matching allowlisted record without resolving ambiguity."""
        result = await self._caller.call_tool(
            "lookup_resources",
            {
                "identifier_kind": identifier.kind.value,
                "identifier_value": identifier.value,
            },
        )
        records = result.get("records")
        if not isinstance(records, list) or not all(
            isinstance(record, Mapping) for record in records
        ):
            raise ResourceDiscoveryMcpError.invalid_records()
        return tuple(dict(record) for record in records)

    async def lookup_batch(
        self,
        identifiers: tuple[ResourceIdentifier, ...],
    ) -> tuple[tuple[ResourceRecord, ...], ...]:
        """Resolve several identifiers through one MCP tool call."""
        result = await self._caller.call_tool(
            "lookup_resources_batch",
            {
                "identifiers": [
                    {
                        "identifier_kind": identifier.kind.value,
                        "identifier_value": identifier.value,
                    }
                    for identifier in identifiers
                ]
            },
        )
        raw_results = result.get("results")
        if not isinstance(raw_results, list):
            raise ResourceDiscoveryMcpError.invalid_records()
        records: list[tuple[ResourceRecord, ...]] = []
        for item in raw_results:
            if not isinstance(item, Mapping):
                raise ResourceDiscoveryMcpError.invalid_records()
            raw_records = item.get("records")
            if not isinstance(raw_records, list) or not all(
                isinstance(record, Mapping) for record in raw_records
            ):
                raise ResourceDiscoveryMcpError.invalid_records()
            records.append(tuple(dict(record) for record in raw_records))
        return tuple(records)
