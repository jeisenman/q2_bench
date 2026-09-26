import asyncio
from collections.abc import Mapping
from typing import cast

import pytest

from domain import AgentRequest, AgentResult
from workspaces.data_engineering.agents.resource_discovery import (
    IdentifierKind,
    ResourceDiscoveryAgent,
    ResourceDiscoveryError,
    ResourceIdentifier,
    ResourceMetadata,
    ResourceSearch,
    SearchStatus,
)


class FakeResourceDiscovery:
    """Replay deterministic Resource Discovery responses."""

    def __init__(
        self,
        records: tuple[Mapping[str, object], ...] = (),
        failure: Exception | None = None,
    ) -> None:
        self.records = records
        self.failure = failure
        self.identifiers: list[str] = []

    async def lookup(self, identifier: object) -> tuple[Mapping[str, object], ...]:
        """Return fixture records or raise the configured provider failure."""
        identifier_value = getattr(identifier, "value", identifier)
        if not isinstance(identifier_value, str):
            pytest.fail("fixture identifier must be text")
        self.identifiers.append(identifier_value)
        if self.failure is not None:
            raise self.failure
        return self.records


def request(identifier: str) -> AgentRequest:
    """Build a request with the identifier in the explicit request attributes."""
    return AgentRequest(
        prompt="Resolve this Resource Discovery identifier.",
        correlation_id="resource-discovery-test",
        attributes=(
            ("identifier_kind", IdentifierKind.CLIENT_ID.value),
            ("identifier_value", identifier),
        ),
    )


def unique_record() -> Mapping[str, object]:
    """Return metadata plus ignored secret-shaped fields for redaction checks."""
    return {
        "client_name": "Example Bank",
        "client_id": "client-123",
        "provisioned_client_id": "provisioned-123",
        "subdomain": "example",
        "environment": "production",
        "zone": "us-east",
        "service": "resource-api",
        "resource_set": "core",
        "database": "example-production",
        "storage": "exampleprod",
        "datalake": "example-lake",
        "reviewed_production_resend_url": (
            "https://us01-app.precisionlender.com/"
            "Admin/Troubleshooting/ResendOpportunitySnapshots"
        ),
        "routing_source": "reviewed-lookup",
        "prod_support_ignore": True,
        "client_secret": "do-not-print-client-secret",
        "access_token": "do-not-print-access-token",
    }


def run_agent(
    source: FakeResourceDiscovery,
    identifier: str,
) -> AgentResult:
    """Run the framework-neutral agent with one deterministic fixture."""
    return asyncio.run(ResourceDiscoveryAgent(source).run(request(identifier)))


def test_agent_reports_a_unique_resource_match() -> None:
    source = FakeResourceDiscovery((unique_record(),))

    result = run_agent(source, "client-123")

    assert result.correlation_id == "resource-discovery-test"
    assert "Finding: unique match" in result.output
    assert "Example Bank" in result.output
    assert "client-123" in result.output
    assert "provisioned-123" in result.output
    assert "production" in result.output
    assert source.identifiers == ["client-123"]
    assert ("status", "unique") in result.attributes
    assert ("identifier_value", "client-123") in result.attributes
    assert ("client_name", "Example Bank") in result.attributes
    assert ("provisioned_client_id", "provisioned-123") in result.attributes
    assert ("environment", "production") in result.attributes
    assert ("prod_support_ignore", True) in result.attributes
    assert (
        "reviewed_production_resend_url",
        (
            "https://us01-app.precisionlender.com/"
            "Admin/Troubleshooting/ResendOpportunitySnapshots"
        ),
    ) in result.attributes
    assert result.tool_calls == ("ResourceDiscovery",)


def test_agent_rejects_an_empty_identifier_before_provider_call() -> None:
    source = FakeResourceDiscovery((unique_record(),))

    with pytest.raises(ResourceDiscoveryError, match="value must not be empty"):
        run_agent(source, " ")

    assert source.identifiers == []


def test_agent_surfaces_provider_failure_without_a_partial_result() -> None:
    source = FakeResourceDiscovery(
        failure=RuntimeError("Resource Discovery API unavailable")
    )

    with pytest.raises(ResourceDiscoveryError, match="API unavailable"):
        run_agent(source, "client-123")


def test_agent_reports_no_match_without_inventing_a_client() -> None:
    result = run_agent(FakeResourceDiscovery(), "missing-client")

    assert "Finding: no unique match" in result.output
    assert "No unique match was returned" in result.output
    assert "Example Bank" not in result.output
    assert ("status", "not_found") in result.attributes


def test_agent_reports_all_ambiguous_matches_deterministically() -> None:
    records = (
        {
            "client_name": "Zulu Bank",
            "client_id": "client-z",
            "environment": "production",
        },
        {
            "client_name": "Alpha Bank",
            "client_id": "client-a",
            "environment": "production",
        },
    )

    result = run_agent(FakeResourceDiscovery(records), "shared-client")

    assert "Finding: Ambiguous matches" in result.output
    assert "Alpha Bank" in result.output
    assert "Zulu Bank" in result.output
    assert result.output.index("Alpha Bank") < result.output.index("Zulu Bank")
    assert "Multiple records matched" in result.output
    assert ("status", "ambiguous") in result.attributes


def test_agent_output_is_deterministic_and_contains_no_secret_fields() -> None:
    source = FakeResourceDiscovery((unique_record(),))

    first = run_agent(source, "client-123").output
    second = run_agent(source, "client-123").output

    assert first == second
    for secret in (
        "client_secret",
        "access_token",
        "password",
        "token",
    ):
        assert secret not in first


def test_agent_accepts_the_legacy_explicit_identifier_attribute() -> None:
    source = FakeResourceDiscovery((unique_record(),))
    request_value = AgentRequest(
        prompt="Resolve this identifier.",
        correlation_id="legacy-request",
        attributes=(("identifier", "resource-123"),),
    )

    result = asyncio.run(ResourceDiscoveryAgent(source).run(request_value))

    assert source.identifiers == ["resource-123"]
    assert ("identifier_kind", IdentifierKind.RESOURCE_ID.value) in result.attributes


def test_agent_rejects_invalid_identifier_configuration() -> None:
    source = FakeResourceDiscovery()
    invalid_kind = AgentRequest(
        prompt="Resolve this identifier.",
        correlation_id="invalid-kind",
        attributes=(
            ("identifier_kind", "unsupported"),
            ("identifier_value", "value"),
        ),
    )
    duplicate = AgentRequest(
        prompt="Resolve this identifier.",
        correlation_id="duplicate",
        attributes=(("identifier", "one"), ("identifier", "two")),
    )

    with pytest.raises(ResourceDiscoveryError, match="identifier_kind must be"):
        asyncio.run(ResourceDiscoveryAgent(source).run(invalid_kind))
    with pytest.raises(ResourceDiscoveryError, match="duplicated"):
        asyncio.run(ResourceDiscoveryAgent(source).run(duplicate))


def test_agent_rejects_invalid_provider_metadata() -> None:
    source = FakeResourceDiscovery(({"client_name": ["not", "text"]},))

    with pytest.raises(ResourceDiscoveryError, match="invalid resource metadata"):
        run_agent(source, "client-123")


def test_resource_models_validate_boundaries_and_statuses() -> None:
    identifier = ResourceIdentifier(IdentifierKind.CLIENT_NAME, "Example Bank")

    assert ResourceSearch(identifier).status is SearchStatus.NOT_FOUND
    assert (
        ResourceSearch(
            identifier,
            (ResourceMetadata(client_name="Example Bank"),),
        ).status
        is SearchStatus.UNIQUE
    )
    with pytest.raises(ValueError, match="at least one field"):
        ResourceMetadata()
    with pytest.raises(TypeError, match="kind must be"):
        ResourceIdentifier(cast(IdentifierKind, "client_name"), "Example Bank")
