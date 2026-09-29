from __future__ import annotations

import asyncio

import pytest

from adapters.mcp import (
    ResourceDiscoveryMcpError,
    ResourceDiscoveryMcpSource,
)
from workspaces.data_engineering.agents.resource_discovery import (
    IdentifierKind,
    ResourceIdentifier,
)

CLIENT_ID = "1f06da19-2f61-401c-a1b7-38902e4f3543"
BATCH_SIZE = 2


class FakeCaller:
    async def call_tool(self, name, arguments):
        assert name == "lookup_resources"
        assert arguments["identifier_value"] == CLIENT_ID
        return {
            "records": [
                {"client_name": "Bank A", "provisioned_client_id": CLIENT_ID},
                {"client_name": "Bank B", "provisioned_client_id": CLIENT_ID},
            ]
        }


class BatchCaller:
    async def call_tool(self, name, arguments):
        assert name == "lookup_resources_batch"
        assert len(arguments["identifiers"]) == BATCH_SIZE
        return {
            "results": [
                {
                    "records": [
                        {"client_name": "Bank A", "provisioned_client_id": CLIENT_ID}
                    ]
                },
                {"records": []},
            ]
        }


def test_resource_discovery_mcp_preserves_ambiguous_matches() -> None:
    source = ResourceDiscoveryMcpSource(FakeCaller())

    records = asyncio.run(
        source.lookup(ResourceIdentifier(IdentifierKind.CLIENT_ID, CLIENT_ID))
    )

    assert [record["client_name"] for record in records] == ["Bank A", "Bank B"]


def test_resource_discovery_mcp_batches_identifiers_in_one_call() -> None:
    source = ResourceDiscoveryMcpSource(BatchCaller())
    identifiers = (
        ResourceIdentifier(IdentifierKind.CLIENT_ID, CLIENT_ID),
        ResourceIdentifier(
            IdentifierKind.CLIENT_ID,
            "11111111-1111-4111-8111-111111111111",
        ),
    )

    records = asyncio.run(source.lookup_batch(identifiers))

    assert records[0][0]["client_name"] == "Bank A"
    assert records[1] == ()


def test_resource_discovery_mcp_rejects_invalid_records() -> None:
    class InvalidCaller:
        async def call_tool(self, name, arguments):
            del name, arguments
            return {"records": "invalid"}

    with pytest.raises(ResourceDiscoveryMcpError, match="list"):
        asyncio.run(
            ResourceDiscoveryMcpSource(InvalidCaller()).lookup(
                ResourceIdentifier(IdentifierKind.CLIENT_ID, CLIENT_ID)
            )
        )
