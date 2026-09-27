"""Build deterministic client UUID and parsed-name lookup indexes."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

from workspaces.data_engineering.agents.resource_discovery.models import (
    IdentifierKind,
    ResourceIdentifier,
)
from workspaces.data_engineering.agents.resource_discovery.ports import ResourceRecord

AUTHORITATIVE_SOURCES = frozenset({"resource-discovery-api", "user-confirmed"})
SCOTIABANK_DATA_VALIDATION = re.compile(
    r"^scotiabank\s*-\s*data\s+validation$",
    re.IGNORECASE,
)
NAME_KEY_CHARACTERS = re.compile(r"[^a-z0-9]+")


def parse_client_name(name: str) -> str:
    """Return the approved display name for one client."""
    normalized = " ".join(name.split())
    if SCOTIABANK_DATA_VALIDATION.fullmatch(normalized):
        return "Scotiabank DV"
    return normalized


def client_name_index_key(name: str) -> str:
    """Return a punctuation-insensitive key for a parsed client name."""
    return NAME_KEY_CHARACTERS.sub(" ", parse_client_name(name).casefold()).strip()


@dataclass(frozen=True, slots=True)
class ClientLookupIndex:
    """Index authoritative client records by UUID and parsed client name."""

    by_uuid: Mapping[str, ResourceRecord]
    by_name: Mapping[str, tuple[ResourceRecord, ...]]

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, object],
    ) -> ClientLookupIndex:
        """Build an immutable index from non-secret quick-lookup metadata."""
        by_uuid: dict[str, ResourceRecord] = {}
        names: dict[str, list[ResourceRecord]] = {}
        for raw_uuid, raw_entry in payload.items():
            if not isinstance(raw_entry, Mapping):
                continue
            record = _record(raw_uuid, raw_entry)
            if record is None:
                continue
            normalized_uuid = str(UUID(raw_uuid))
            by_uuid[normalized_uuid] = record
            original_name = raw_entry["name"]
            assert isinstance(original_name, str)
            for name in {original_name, str(record["client_name"])}:
                names.setdefault(client_name_index_key(name), []).append(record)
        return cls(
            MappingProxyType(by_uuid),
            MappingProxyType(
                {
                    key: tuple(sorted(records, key=_record_uuid))
                    for key, records in names.items()
                }
            ),
        )

    def lookup(
        self,
        identifier: ResourceIdentifier,
    ) -> tuple[ResourceRecord, ...]:
        """Return indexed records for a supported client identifier."""
        if identifier.kind is IdentifierKind.CLIENT_ID:
            try:
                normalized = str(UUID(identifier.value))
            except ValueError:
                return ()
            record = self.by_uuid.get(normalized)
            return (record,) if record is not None else ()
        if identifier.kind is IdentifierKind.CLIENT_NAME:
            return self.by_name.get(client_name_index_key(identifier.value), ())
        return ()


def _record(
    client_uuid: str,
    entry: Mapping[str, object],
) -> ResourceRecord | None:
    name = entry.get("name")
    source = entry.get("source")
    api_status = entry.get("api_status")
    if (
        not isinstance(name, str)
        or not name.strip()
        or source not in AUTHORITATIVE_SOURCES
        or (api_status != "unique-match" and source != "user-confirmed")
    ):
        return None
    normalized_uuid = str(UUID(client_uuid))
    record: dict[str, object] = {
        "provisioned_client_id": normalized_uuid,
        "client_name": parse_client_name(name),
        "routing_source": f"local-client-index:{source}",
    }
    for field_name in ("subdomain", "reviewed_production_resend_url"):
        value = entry.get(field_name)
        if isinstance(value, str) and value.strip():
            record[field_name] = value
    ignore = entry.get("prod_support_ignore")
    if isinstance(ignore, bool):
        record["prod_support_ignore"] = ignore
    return record


def _record_uuid(record: ResourceRecord) -> str:
    value = record.get("provisioned_client_id")
    return value if isinstance(value, str) else ""
