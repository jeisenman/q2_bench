"""Immutable contracts for read-only resource discovery."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


def _require_text(value: str, field_name: str) -> None:
    """Reject blank text at a model boundary."""
    if not isinstance(value, str):
        message = f"{field_name} must be a string"
        raise TypeError(message)
    if not value.strip():
        message = f"{field_name} must not be empty"
        raise ValueError(message)


def _require_optional_text(value: str | None, field_name: str) -> None:
    """Reject blank optional text while preserving absent values."""
    if value is not None:
        _require_text(value, field_name)


class IdentifierKind(StrEnum):
    """Supported non-secret fields for resource searches."""

    CLIENT_ID = "client_id"
    CLIENT_NAME = "client_name"
    SUBDOMAIN = "subdomain"
    RESOURCE_ID = "resource_id"
    RESOURCE_SET = "resource_set"
    ENVIRONMENT = "environment"
    DATABASE = "database"
    STORAGE = "storage"
    DATALAKE = "datalake"


class SearchStatus(StrEnum):
    """Cardinality of a resource search."""

    NOT_FOUND = "not_found"
    UNIQUE = "unique"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class ResourceIdentifier:
    """Identify one read-only search field and its non-secret value."""

    kind: IdentifierKind
    value: str

    def __post_init__(self) -> None:
        """Validate the search identifier."""
        if not isinstance(self.kind, IdentifierKind):
            message = "kind must be an IdentifierKind"
            raise TypeError(message)
        _require_text(self.value, "value")

    def __eq__(self, other: object) -> bool:
        """Compare identifiers by value when a legacy source expects text."""
        if isinstance(other, ResourceIdentifier):
            return self.kind is other.kind and self.value == other.value
        if isinstance(other, str):
            return self.value == other
        return False

    def __hash__(self) -> int:
        """Hash the stable identifier value."""
        return hash(self.value)


@dataclass(frozen=True, slots=True)
class ResourceMetadata:
    """Allowlisted client and resource metadata returned by a source."""

    resource_id: str | None = None
    resource_name: str | None = None
    resource_type: str | None = None
    provisioned_client_id: str | None = None
    client_id: str | None = None
    client_name: str | None = None
    subdomain: str | None = None
    environment: str | None = None
    zone: str | None = None
    service: str | None = None
    resource_set: str | None = None
    database: str | None = None
    storage: str | None = None
    datalake: str | None = None

    def __post_init__(self) -> None:
        """Validate allowlisted metadata without accepting arbitrary fields."""
        fields = (
            ("resource_id", self.resource_id),
            ("resource_name", self.resource_name),
            ("resource_type", self.resource_type),
            ("provisioned_client_id", self.provisioned_client_id),
            ("client_id", self.client_id),
            ("client_name", self.client_name),
            ("subdomain", self.subdomain),
            ("environment", self.environment),
            ("zone", self.zone),
            ("service", self.service),
            ("resource_set", self.resource_set),
            ("database", self.database),
            ("storage", self.storage),
            ("datalake", self.datalake),
        )
        for field_name, value in fields:
            _require_optional_text(value, field_name)
        if not any(value is not None for _, value in fields):
            message = "resource metadata must contain at least one field"
            raise ValueError(message)

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> ResourceMetadata:
        """Create metadata from an untrusted record using a safe allowlist."""
        values: dict[str, str | None] = {}
        for field_name in (
            "resource_id",
            "resource_name",
            "resource_type",
            "provisioned_client_id",
            "client_id",
            "client_name",
            "subdomain",
            "environment",
            "zone",
            "service",
            "resource_set",
            "database",
            "storage",
            "datalake",
        ):
            value = record.get(field_name)
            if value is not None and not isinstance(value, str):
                message = f"{field_name} must be a string when present"
                raise TypeError(message)
            values[field_name] = value
        return cls(**values)


@dataclass(frozen=True, slots=True)
class ResourceSearch:
    """Represent one identifier search and its ordered non-secret matches."""

    identifier: ResourceIdentifier
    matches: tuple[ResourceMetadata, ...] = ()

    def __post_init__(self) -> None:
        """Validate the immutable search result boundary."""
        if not isinstance(self.identifier, ResourceIdentifier):
            message = "identifier must be a ResourceIdentifier"
            raise TypeError(message)
        if not isinstance(self.matches, tuple):
            message = "matches must be a tuple"
            raise TypeError(message)
        if any(not isinstance(metadata, ResourceMetadata) for metadata in self.matches):
            message = "matches must contain ResourceMetadata values"
            raise TypeError(message)

    @property
    def status(self) -> SearchStatus:
        """Return explicit result cardinality."""
        if not self.matches:
            return SearchStatus.NOT_FOUND
        if len(self.matches) == 1:
            return SearchStatus.UNIQUE
        return SearchStatus.AMBIGUOUS
