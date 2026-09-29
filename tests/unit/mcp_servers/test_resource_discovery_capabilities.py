from __future__ import annotations

import asyncio
from pathlib import Path

from mcp_servers import resource_discovery

CLIENT_ID = "1f06da19-2f61-401c-a1b7-38902e4f3543"


def test_resource_discovery_server_loads_dotenv_without_overwriting_environment(
    monkeypatch,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        'RESOURCE_DISCOVERY_SCOPE="api://scope/.default"\n'
        "RESOURCE_DISCOVERY_CLIENT_ID=file-client\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RESOURCE_DISCOVERY_CLIENT_ID", "exported-client")

    resource_discovery.configure_environment(env_file)

    assert (
        resource_discovery.os.environ["RESOURCE_DISCOVERY_SCOPE"]
        == "api://scope/.default"
    )
    assert (
        resource_discovery.os.environ["RESOURCE_DISCOVERY_CLIENT_ID"]
        == "exported-client"
    )


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
