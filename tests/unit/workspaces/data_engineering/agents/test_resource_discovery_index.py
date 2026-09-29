"""Tests for deterministic local client identity indexing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from workspaces.data_engineering.agents.resource_discovery import (
    ClientLookupIndex,
    IdentifierKind,
    ResourceIdentifier,
    parse_client_name,
)

LOOKUP_PATH = (
    Path(__file__).resolve().parents[5]
    / ".codex"
    / "skills"
    / "resource-discovery"
    / "references"
    / "client-guuid-lookup.json"
)
PREVIOUSLY_UNRESOLVED_CLIENTS = (
    ("022312e6-2997-4156-bf22-921fdb1cbf40", "Wells Fargo - PL Data Validation"),
    ("385c35bf-29c4-48a7-9527-a91963b7af69", "U.S. Bancorp (Minneapolis, MN)"),
    ("49f3873c-deb0-4846-88bd-4628cef8abfe", "Renasant Bank (Tupelo, MS)"),
    ("5301628b-e85f-4ff9-b5b3-e8d13c5926a7", "TD Bank (Wilmington, DE)"),
    ("60009dc8-695b-4b58-b512-1fc72c3c98e7", "Popular Community Bank"),
    ("792f7424-402e-4a7e-b4de-69f811435d9c", "BoFA"),
    ("951ddcc6-dc43-408e-a4f4-bf0a67015ccc", "Synovus Bank (Columbus, GA)"),
    ("9d272969-2cdd-401b-a373-6a73cf5a3042", "Glacier Bancorp"),
    ("9e344fed-d096-4827-8985-992c8a021369", "Webster Bank"),
    ("dff9e5f7-c60a-4e43-b7a9-845ab44f34d0", "Atlantic Union Bank (Richmond, VA)"),
)
SCOTIABANK_DV_UUID = "b4916353-ef8a-4af8-9601-74305858e905"
BANK_OF_HOPE_CA_UUID = "b0302b2c-6dd3-4675-bfe1-cef65acc37d5"


def client_index() -> ClientLookupIndex:
    """Load the repository's maintained non-secret client lookup."""
    payload = json.loads(LOOKUP_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return ClientLookupIndex.from_mapping(payload)


@pytest.mark.parametrize(
    ("client_uuid", "expected_name"),
    PREVIOUSLY_UNRESOLVED_CLIENTS,
)
def test_index_resolves_previously_unresolved_clients(
    client_uuid: str,
    expected_name: str,
) -> None:
    records = client_index().lookup(
        ResourceIdentifier(IdentifierKind.CLIENT_ID, client_uuid)
    )

    assert len(records) == 1
    assert records[0]["client_name"] == expected_name
    assert records[0]["provisioned_client_id"] == client_uuid


def test_index_supports_original_and_parsed_client_names() -> None:
    index = client_index()

    full_name = index.lookup(
        ResourceIdentifier(
            IdentifierKind.CLIENT_NAME,
            "Scotiabank - Data Validation",
        )
    )
    parsed_name = index.lookup(
        ResourceIdentifier(IdentifierKind.CLIENT_NAME, "Scotiabank DV")
    )

    assert full_name == parsed_name
    assert full_name[0]["client_name"] == "Scotiabank DV"
    assert full_name[0]["provisioned_client_id"] == SCOTIABANK_DV_UUID
    assert parse_client_name("  Scotiabank - Data Validation ") == "Scotiabank DV"


def test_index_resolves_user_confirmed_bank_of_hope_ca_resources() -> None:
    records = client_index().lookup(
        ResourceIdentifier(IdentifierKind.CLIENT_ID, BANK_OF_HOPE_CA_UUID)
    )

    assert records == (
        {
            "provisioned_client_id": BANK_OF_HOPE_CA_UUID,
            "client_name": "Bank of Hope CA",
            "routing_source": "local-client-index:user-confirmed",
            "client_id": "3424-01",
            "subdomain": "bankofhopeca",
            "environment": "US01",
            "service": "DTS DIBS",
            "resource_id": "6374b186-73b5-4228-9301-60c62c423235",
            "resource_set": "DIBS - Q2 OLB - Production",
        },
    )


def test_index_rejects_non_authoritative_and_invalid_lookup_values() -> None:
    index = ClientLookupIndex.from_mapping(
        {
            "022312e6-2997-4156-bf22-921fdb1cbf40": {
                "name": "Unresolved Client",
                "source": "unresolved",
                "api_status": "no-match",
            }
        }
    )

    assert (
        index.lookup(
            ResourceIdentifier(
                IdentifierKind.CLIENT_ID,
                "022312e6-2997-4156-bf22-921fdb1cbf40",
            )
        )
        == ()
    )
    with pytest.raises(ValueError, match="client_id must be a complete UUID"):
        ResourceIdentifier(IdentifierKind.CLIENT_ID, "not-a-uuid")
