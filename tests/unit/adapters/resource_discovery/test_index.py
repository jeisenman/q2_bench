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

    async def lookup(
        self,
        identifier: ResourceIdentifier,
    ) -> tuple[Mapping[str, object], ...]:
        """Return the configured records."""
        del identifier
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


def test_unique_primary_result_wins_over_local_index(tmp_path: Path) -> None:
    primary = FakeSource(({"client_name": "Live API Name"},))
    source = IndexedResourceDiscoverySource(
        primary,
        write_lookup(tmp_path / "lookup.json"),
    )

    assert asyncio.run(source.lookup(identifier())) == (
        {"client_name": "Live API Name"},
    )


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


@pytest.mark.parametrize("contents", ["[]", "{invalid"])
def test_json_lookup_rejects_invalid_payloads(
    tmp_path: Path,
    contents: str,
) -> None:
    path = tmp_path / "lookup.json"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(ClientLookupIndexError):
        JsonClientLookupSource(path)
