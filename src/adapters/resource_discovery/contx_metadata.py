"""Read non-secret client resource metadata from a local Contx checkout."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from workspaces.data_engineering.agents.resource_discovery import ResourceRecord

CONTX_ENVIRONMENTS = frozenset({"alpha", "production", "staging"})
CONTX_RESOURCE_TYPES = frozenset({"all", "database", "datalake", "storage"})
CLIENT_GROUP_SUFFIX = re.compile(r"-client$", re.IGNORECASE)
NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")


class ContxMetadataError(ValueError):
    """Raised when Contx metadata or a resource query is invalid."""

    @classmethod
    def invalid_client_id(cls) -> ContxMetadataError:
        """Return an error for an invalid client UUID."""
        return cls("Contx client_id must be a complete UUID")

    @classmethod
    def invalid_client_name(cls) -> ContxMetadataError:
        """Return an error for a blank client name."""
        return cls("Contx client_name must not be empty")

    @classmethod
    def invalid_choice(
        cls,
        field_name: str,
        allowed_values: frozenset[str],
    ) -> ContxMetadataError:
        """Return an error for an unsupported query choice."""
        allowed = ", ".join(sorted(allowed_values))
        return cls(f"Contx {field_name} must be one of: {allowed}")

    @classmethod
    def invalid_resource_kind(cls) -> ContxMetadataError:
        """Return an error for a blank exact resource kind."""
        return cls("Contx resource_kind must not be empty when supplied")

    @classmethod
    def invalid_instances(cls, path: Path) -> ContxMetadataError:
        """Return an error for a malformed datastore instance collection."""
        return cls(f"{path}: instances must be an array")

    @classmethod
    def client_not_found(cls, client_name: str) -> ContxMetadataError:
        """Return an error when no source resolves a client name."""
        return cls(f"no unique client UUID was found for {client_name!r}")

    @classmethod
    def ambiguous_client(cls, client_name: str) -> ContxMetadataError:
        """Return an error when identity lookup finds several client UUIDs."""
        return cls(f"multiple client UUIDs matched {client_name!r}")

    @classmethod
    def unreadable(cls, path: Path, error: Exception) -> ContxMetadataError:
        """Return an error for missing or invalid JSON metadata."""
        return cls(f"unable to load Contx metadata {path}: {error}")

    @classmethod
    def invalid_collection(
        cls,
        path: Path,
        key: str,
        expected: str,
    ) -> ContxMetadataError:
        """Return an error for a malformed top-level metadata collection."""
        return cls(f"{path}: {key} must be {expected}")

    @classmethod
    def partition_not_found(cls, client_id: str) -> ContxMetadataError:
        """Return an error when Contx has no matching client partition."""
        return cls(f"Contx has no partition for client {client_id}")

    @classmethod
    def ambiguous_partition(cls, client_id: str) -> ContxMetadataError:
        """Return an error when Contx repeats a client partition."""
        return cls(f"Contx has multiple partitions for client {client_id}")


@dataclass(frozen=True, slots=True)
class ContxResourceQuery:
    """Select effective resources for one client partition."""

    client_id: str
    client_name: str
    environment: str = "production"
    resource_type: str = "all"
    resource_kind: str | None = None

    def __post_init__(self) -> None:
        """Validate the query at the adapter boundary."""
        try:
            UUID(self.client_id)
        except (TypeError, ValueError) as error:
            raise ContxMetadataError.invalid_client_id() from error
        if not self.client_name.strip():
            raise ContxMetadataError.invalid_client_name()
        if self.environment not in CONTX_ENVIRONMENTS:
            raise ContxMetadataError.invalid_choice(
                "environment",
                CONTX_ENVIRONMENTS,
            )
        if self.resource_type not in CONTX_RESOURCE_TYPES:
            raise ContxMetadataError.invalid_choice(
                "resource_type",
                CONTX_RESOURCE_TYPES,
            )
        if self.resource_kind is not None and not self.resource_kind.strip():
            raise ContxMetadataError.invalid_resource_kind()


class ContxMetadataSource:
    """Resolve a client partition to its effective Contx datastore instances."""

    def __init__(self, repository: Path) -> None:
        """Create a source for one explicit Contx checkout."""
        self.repository = repository.expanduser()

    async def resolve_client_id(
        self,
        client_name: str,
        *,
        environment: str = "production",
    ) -> str:
        """Resolve one exact client-group name to its partition UUID."""
        if environment not in CONTX_ENVIRONMENTS:
            raise ContxMetadataError.invalid_choice(
                "environment",
                CONTX_ENVIRONMENTS,
            )
        return await asyncio.to_thread(
            self._resolve_client_id,
            client_name,
            environment,
        )

    async def lookup(
        self,
        query: ContxResourceQuery,
    ) -> tuple[ResourceRecord, ...]:
        """Return safe effective resources for the client and query."""
        return await asyncio.to_thread(self._lookup, query)

    def _resolve_client_id(self, client_name: str, environment: str) -> str:
        metadata = self.repository / "Metadata" / environment
        partitions = _metadata_array(
            metadata / "application_partitions.json",
            "ApplicationPartitionsMetadata",
        )
        requested_key = _client_key(client_name)
        matches = tuple(
            item
            for item in partitions
            if isinstance(item, Mapping)
            and _client_group_key(item.get("client_group")) == requested_key
        )
        if not matches:
            raise ContxMetadataError.client_not_found(client_name)
        if len(matches) != 1:
            raise ContxMetadataError.ambiguous_client(client_name)
        client_id = matches[0].get("name")
        if not isinstance(client_id, str):
            raise ContxMetadataError.invalid_client_id()
        try:
            return str(UUID(client_id))
        except ValueError as error:
            raise ContxMetadataError.invalid_client_id() from error

    def _lookup(self, query: ContxResourceQuery) -> tuple[ResourceRecord, ...]:
        metadata = self.repository / "Metadata" / query.environment
        partitions = _metadata_array(
            metadata / "application_partitions.json",
            "ApplicationPartitionsMetadata",
        )
        datastores = _metadata_object(
            metadata / "datastores.json",
            "DatastoresMetadata",
        )
        partition = _partition(partitions, query.client_id)
        instances = datastores.get("instances")
        if not isinstance(instances, list):
            raise ContxMetadataError.invalid_instances(metadata / "datastores.json")
        selected = _effective_instances(partition, instances, query)
        return tuple(
            _safe_record(instance, partition, query, group)
            for instance, group in selected
        )


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContxMetadataError.unreadable(path, error) from error


def _metadata_array(path: Path, key: str) -> list[object]:
    payload = _read_json(path)
    if not isinstance(payload, Mapping):
        raise ContxMetadataError.invalid_collection(path, key, "an array")
    collection = payload.get(key)
    if not isinstance(collection, list):
        raise ContxMetadataError.invalid_collection(path, key, "an array")
    return collection


def _metadata_object(path: Path, key: str) -> Mapping[str, object]:
    payload = _read_json(path)
    if not isinstance(payload, Mapping):
        raise ContxMetadataError.invalid_collection(path, key, "an object")
    collection = payload.get(key)
    if not isinstance(collection, Mapping):
        raise ContxMetadataError.invalid_collection(path, key, "an object")
    return collection


def _partition(
    partitions: list[object],
    client_id: str,
) -> Mapping[str, object]:
    matches = tuple(
        item
        for item in partitions
        if isinstance(item, Mapping) and item.get("name") == client_id
    )
    if not matches:
        raise ContxMetadataError.partition_not_found(client_id)
    if len(matches) != 1:
        raise ContxMetadataError.ambiguous_partition(client_id)
    return matches[0]


def _effective_instances(
    partition: Mapping[str, object],
    instances: list[object],
    query: ContxResourceQuery,
) -> tuple[tuple[Mapping[str, object], str], ...]:
    client_group = _optional_text(partition.get("client_group"))
    shared_group = _optional_text(partition.get("shared_group"))
    matching = tuple(
        instance
        for instance in instances
        if isinstance(instance, Mapping) and _matches_resource(instance, query)
    )
    kinds = sorted(
        {
            kind.casefold(): kind
            for instance in matching
            if (kind := _optional_text(instance.get("kind"))) is not None
        }.values(),
        key=str.casefold,
    )
    selected: list[tuple[Mapping[str, object], str]] = []
    for kind in kinds:
        kind_instances = tuple(
            instance for instance in matching if instance.get("kind") == kind
        )
        client_matches = _in_group(kind_instances, client_group)
        if client_matches:
            selected.extend(
                (instance, client_group or "") for instance in client_matches
            )
            continue
        shared_matches = _in_group(kind_instances, shared_group)
        selected.extend((instance, shared_group or "") for instance in shared_matches)
    return tuple(sorted(selected, key=lambda item: _record_sort_key(item[0])))


def _matches_resource(
    instance: Mapping[str, object],
    query: ContxResourceQuery,
) -> bool:
    kind = _optional_text(instance.get("kind"))
    if kind is None:
        return False
    if query.resource_kind is not None:
        return kind.casefold() == query.resource_kind.casefold()
    if query.resource_type == "all":
        return True
    if query.resource_type == "database":
        return _optional_text(instance.get("database")) is not None
    return _storage_field(kind, instance) == query.resource_type


def _storage_field(
    kind: str,
    instance: Mapping[str, object],
) -> str | None:
    host = _optional_text(instance.get("host_name"))
    domain = _optional_text(instance.get("domain"))
    if host is None:
        return None
    lowered = kind.casefold()
    if "adls" in lowered or domain == "dfs.core.windows.net":
        return "datalake"
    if "storage" in lowered or "blob" in lowered or domain == "blob.core.windows.net":
        return "storage"
    return None


def _in_group(
    instances: tuple[Mapping[str, object], ...],
    group: str | None,
) -> tuple[Mapping[str, object], ...]:
    if group is None:
        return ()
    matches: list[Mapping[str, object]] = []
    for instance in instances:
        groups = instance.get("groups")
        if isinstance(groups, list) and group in groups:
            matches.append(instance)
    return tuple(matches)


def _safe_record(
    instance: Mapping[str, object],
    partition: Mapping[str, object],
    query: ContxResourceQuery,
    group: str,
) -> ResourceRecord:
    kind = _optional_text(instance.get("kind"))
    assert kind is not None
    host = _optional_text(instance.get("host_name"))
    domain = _optional_text(instance.get("domain"))
    storage_field = _storage_field(kind, instance)
    record: dict[str, object] = {
        "client_name": query.client_name,
        "provisioned_client_id": query.client_id,
        "environment": query.environment,
        "zone": _optional_text(partition.get("zone")),
        "resource_set": group,
        "resource_name": _optional_text(instance.get("name")),
        "resource_type": kind,
        "database": _optional_text(instance.get("database")),
        "database_server": _qualified_host(host, domain),
        "region": _optional_text(instance.get("region")),
        "resource_group": _optional_text(instance.get("resource_group_name")),
        "protocol": _optional_text(instance.get("protocol")),
        "path": _optional_text(instance.get("path")),
        "port": instance.get("port") if isinstance(instance.get("port"), int) else None,
        "routing_source": "contx-metadata",
    }
    if storage_field is not None:
        record[storage_field] = host
    return {key: value for key, value in record.items() if value is not None}


def _client_key(value: str) -> str:
    return NON_ALPHANUMERIC.sub("", value.casefold())


def _client_group_key(value: object) -> str | None:
    group = _optional_text(value)
    if group is None:
        return None
    return _client_key(CLIENT_GROUP_SUFFIX.sub("", group))


def _qualified_host(host: str | None, domain: str | None) -> str | None:
    if host is None:
        return None
    return f"{host}.{domain}" if domain is not None else host


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _record_sort_key(record: Mapping[str, object]) -> tuple[str, str]:
    kind = record.get("kind")
    name = record.get("name")
    return (
        kind.casefold() if isinstance(kind, str) else "",
        name.casefold() if isinstance(name, str) else "",
    )
