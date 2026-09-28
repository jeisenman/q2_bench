"""Tests for the local Resource Discovery identity fallback."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from adapters.resource_discovery import (
    ClientLookupIndexError,
    IndexedResourceDiscoverySource,
    JsonClientLookupSource,
)
from workspaces.data_engineering.agents.resource_discovery import (
    IdentifierKind,
    ResourceIdentifier,
)

CLIENT_UUID = "49f3873c-deb0-4846-88bd-4628cef8abfe"


class FakeSource:
    """Return deterministic records from a provider boundary."""

    def __init__(self, records: tuple[Mapping[str, object], ...]) -> None:
        self.records = records
        self.calls = 0

    async def lookup(
        self,
        identifier: ResourceIdentifier,
    ) -> tuple[Mapping[str, object], ...]:
        """Return the configured records."""
        del identifier
        self.calls += 1
        return self.records


def write_lookup(path: Path) -> JsonClientLookupSource:
    """Write one authoritative local lookup record."""
    path.write_text(
        json.dumps(
            {
                CLIENT_UUID: {
                    "name": "Renasant Bank (Tupelo, MS)",
                    "source": "resource-discovery-api",
                    "api_status": "unique-match",
                }
            }
        ),
        encoding="utf-8",
    )
    return JsonClientLookupSource(path)


def identifier() -> ResourceIdentifier:
    """Build the shared client identifier."""
    return ResourceIdentifier(IdentifierKind.CLIENT_ID, CLIENT_UUID)


def test_unique_local_result_short_circuits_primary(tmp_path: Path) -> None:
    primary = FakeSource(({"client_name": "Live API Name"},))
    source = IndexedResourceDiscoverySource(
        primary,
        write_lookup(tmp_path / "lookup.json"),
    )

    records = asyncio.run(source.lookup(identifier()))

    assert records[0]["client_name"] == "Renasant Bank (Tupelo, MS)"
    assert primary.calls == 0


@pytest.mark.parametrize(
    "primary_records",
    [
        (),
        ({"client_name": "One"}, {"client_name": "Two"}),
    ],
)
def test_non_unique_primary_uses_authoritative_local_index(
    tmp_path: Path,
    primary_records: tuple[Mapping[str, object], ...],
) -> None:
    source = IndexedResourceDiscoverySource(
        FakeSource(primary_records),
        write_lookup(tmp_path / "lookup.json"),
    )

    records = asyncio.run(source.lookup(identifier()))

    assert records[0]["client_name"] == "Renasant Bank (Tupelo, MS)"
    assert records[0]["routing_source"].startswith("local-client-index:")


def test_missing_local_fallback_preserves_ambiguous_api_results(tmp_path: Path) -> None:
    ambiguous = ({"client_name": "One"}, {"client_name": "Two"})
    source = IndexedResourceDiscoverySource(
        FakeSource(ambiguous),
        write_lookup(tmp_path / "lookup.json"),
    )

    assert (
        asyncio.run(
            source.lookup(
                ResourceIdentifier(
                    IdentifierKind.CLIENT_ID,
                    "022312e6-2997-4156-bf22-921fdb1cbf40",
                )
            )
        )
        == ambiguous
    )


def test_local_index_generates_acronym_candidates(tmp_path: Path) -> None:
    source = write_lookup(tmp_path / "lookup.json")

    records = asyncio.run(source.alias_candidates("RB"))

    assert records[0]["client_name"] == "Renasant Bank (Tupelo, MS)"


def test_local_index_exposes_confirmed_operational_resource_fields(
    tmp_path: Path,
) -> None:
    path = tmp_path / "lookup.json"
    path.write_text(
        json.dumps(
            {
                CLIENT_UUID: {
                    "api_status": "no-unique-match",
                    "client_id": "fa00b19e-33d9-4f03-b26d-88ff801c19c0",
                    "environment": "US01",
                    "name": "City National Bank",
                    "resource_id": "9189ffa8-c2a4-4ca4-b3c3-5f1b4458270b",
                    "resource_set": "CNB Production",
                    "service": "PLApp",
                    "source": "user-confirmed",
                    "subdomain": "cnb",
                }
            }
        ),
        encoding="utf-8",
    )

    records = asyncio.run(JsonClientLookupSource(path).lookup(identifier()))

    assert records == (
        {
            "provisioned_client_id": CLIENT_UUID,
            "client_name": "City National Bank",
            "routing_source": "local-client-index:user-confirmed",
            "client_id": "fa00b19e-33d9-4f03-b26d-88ff801c19c0",
            "subdomain": "cnb",
            "environment": "US01",
            "service": "PLApp",
            "resource_id": "9189ffa8-c2a4-4ca4-b3c3-5f1b4458270b",
            "resource_set": "CNB Production",
        },
    )


@pytest.mark.parametrize("contents", ["[]", "{invalid"])
def test_json_lookup_rejects_invalid_payloads(
    tmp_path: Path,
    contents: str,
) -> None:
    path = tmp_path / "lookup.json"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(ClientLookupIndexError):
        JsonClientLookupSource(path)
