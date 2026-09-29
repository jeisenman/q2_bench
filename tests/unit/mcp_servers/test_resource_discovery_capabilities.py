from __future__ import annotations

import asyncio

from mcp_servers import resource_discovery

CLIENT_ID = "1f06da19-2f61-401c-a1b7-38902e4f3543"


class FakeSource:
    async def lookup(self, identifier):
        assert identifier.value == CLIENT_ID
        return (
            {
                "client_name": "Example Bank",
                "provisioned_client_id": CLIENT_ID,
            },
        )


def test_resource_discovery_server_batches_allowlisted_records(monkeypatch) -> None:
    monkeypatch.setattr(resource_discovery, "_source", FakeSource)

    result = asyncio.run(
        resource_discovery.lookup_resources_batch(
            [
                {
                    "identifier_kind": "client_id",
                    "identifier_value": CLIENT_ID,
                }
            ]
        )
    )

    assert result["count"] == 1
    assert result["results"][0]["records"][0]["client_name"] == "Example Bank"


def test_resource_discovery_server_returns_allowlisted_records(monkeypatch) -> None:
    monkeypatch.setattr(resource_discovery, "_source", FakeSource)

    result = asyncio.run(resource_discovery.lookup_resources("client_id", CLIENT_ID))

    assert result["count"] == 1
    assert result["records"][0]["client_name"] == "Example Bank"
