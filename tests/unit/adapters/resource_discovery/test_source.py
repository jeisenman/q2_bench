import asyncio
from urllib.parse import parse_qs, urlparse
from urllib.request import Request

import pytest

from adapters.resource_discovery import (
    ResourceDiscoveryApiError,
    ResourceDiscoveryApiSource,
    ResourceDiscoveryConfig,
)
from workspaces.data_engineering.agents.resource_discovery import (
    IdentifierKind,
    ResourceIdentifier,
)


class FakeTransport:
    """Return deterministic authentication and lookup responses."""

    def __init__(self, search_response: object) -> None:
        self.search_response = search_response
        self.requests: list[Request] = []

    def request(self, request: Request) -> object:
        self.requests.append(request)
        if request.method == "POST":
            return {"access_token": "secret-token"}
        return self.search_response


def config() -> ResourceDiscoveryConfig:
    return ResourceDiscoveryConfig(
        base_url="https://resources.example.test",
        tenant_id="tenant",
        client_id="client",
        client_secret="secret",
        scope="api://resources/.default",
    )


def test_source_authenticates_and_normalizes_client_lookup() -> None:
    transport = FakeTransport(
        [
            {
                "name": "Example Bank",
                "provisionedClientId": "client-123",
                "subdomain": "example",
                "clientSecret": "must-not-cross-boundary",
            }
        ]
    )
    source = ResourceDiscoveryApiSource(config(), transport)

    records = asyncio.run(
        source.lookup(ResourceIdentifier(IdentifierKind.CLIENT_ID, "client-123"))
    )

    assert records == (
        {
            "client_name": "Example Bank",
            "provisioned_client_id": "client-123",
            "subdomain": "example",
        },
    )
    lookup = transport.requests[1]
    assert urlparse(lookup.full_url).path == "/api/v1/clients"
    assert parse_qs(urlparse(lookup.full_url).query) == {
        "provisionedClientId": ["client-123"]
    }
    assert lookup.get_header("Authorization") == "Bearer secret-token"


def test_source_queries_resource_endpoint_for_resource_fields() -> None:
    transport = FakeTransport({"resourceId": "resource-1", "database": "db"})
    source = ResourceDiscoveryApiSource(config(), transport)

    records = asyncio.run(
        source.lookup(ResourceIdentifier(IdentifierKind.DATABASE, "db"))
    )

    assert records == ({"resource_id": "resource-1", "database": "db"},)
    lookup = transport.requests[1]
    assert urlparse(lookup.full_url).path == "/api/v1/resources"
    assert parse_qs(urlparse(lookup.full_url).query) == {"database": ["db"]}


def test_source_rejects_invalid_api_shapes() -> None:
    source = ResourceDiscoveryApiSource(config(), FakeTransport("invalid"))

    with pytest.raises(ResourceDiscoveryApiError, match="object or list"):
        asyncio.run(
            source.lookup(ResourceIdentifier(IdentifierKind.CLIENT_ID, "client-123"))
        )


def test_source_requires_complete_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "RESOURCE_DISCOVERY_BASE_URL",
        "RESOURCE_DISCOVERY_TENANT_ID",
        "RESOURCE_DISCOVERY_CLIENT_ID",
        "RESOURCE_DISCOVERY_CLIENT_SECRET",
        "RESOURCE_DISCOVERY_SCOPE",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ResourceDiscoveryApiError, match="BASE_URL"):
        ResourceDiscoveryApiSource.from_environment()
