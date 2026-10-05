"""Immutable contracts for repository-derived OpenLineage graphs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Self

from workspaces.data_engineering.workflows.lineage.allocation_models import (
    JobAllocation,
)
from workspaces.data_engineering.workflows.lineage.errors import (
    LineageValidationError,
)


class NodeKind(StrEnum):
    """Kinds of entities represented in a lineage graph."""

    DATASET = "dataset"
    JOB = "job"


class EdgeKind(StrEnum):
    """Supported directed lineage relationships."""

    CONSUMES = "consumes"
    DEPENDS_ON = "depends_on"
    PRODUCES = "produces"


@dataclass(frozen=True, slots=True)
class CanonicalIdentifier:
    """OpenLineage-compatible namespace and name for one entity."""

    kind: NodeKind
    namespace: str
    name: str

    def __post_init__(self) -> None:
        """Reject incomplete canonical identifiers."""
        if not self.namespace.strip():
            raise LineageValidationError.empty_identifier("namespace")
        if not self.name.strip():
            raise LineageValidationError.empty_identifier("name")

    @property
    def value(self) -> str:
        """Return the stable graph identifier."""
        return f"{self.kind.value}:{self.namespace}/{self.name}"

    def to_dict(self) -> dict[str, str]:
        """Serialize the identifier."""
        return {
            "id": self.value,
            "kind": self.kind.value,
            "namespace": self.namespace,
            "name": self.name,
        }


@dataclass(frozen=True, slots=True)
class SourceLocation:
    """Repository source location supporting one lineage assertion."""

    path: str
    line: int

    def to_dict(self) -> dict[str, object]:
        """Serialize the source location."""
        return {"path": self.path, "line": self.line}


@dataclass(frozen=True, slots=True)
class DatasetField:
    """One statically extracted dataset or Snowflake field."""

    name: str
    data_type: str
    nullable: bool = True
    description: str | None = None
    is_pii: bool = False

    def to_dict(self) -> dict[str, object]:
        """Serialize the field."""
        return {
            "name": self.name,
            "type": self.data_type,
            "nullable": self.nullable,
            "description": self.description,
            "isPii": self.is_pii,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        """Deserialize a field."""
        return cls(
            name=str(value["name"]),
            data_type=str(value["type"]),
            nullable=bool(value.get("nullable", True)),
            description=_optional_string(value.get("description")),
            is_pii=bool(value.get("isPii", False)),
        )


@dataclass(frozen=True, slots=True)
class DatasetLocation:
    """One physical materialization of a logical dataset."""

    resource: str
    path_convention: str | None = None
    role: str = "output"

    def to_dict(self) -> dict[str, object]:
        """Serialize the physical location."""
        return {
            "resource": self.resource,
            "pathConvention": self.path_convention,
            "role": self.role,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        """Deserialize a physical location."""
        return cls(
            resource=str(value["resource"]),
            path_convention=_optional_string(value.get("pathConvention")),
            role=str(value.get("role", "output")),
        )


@dataclass(frozen=True, slots=True)
class Transformation:
    """One mechanical repository task condensed into a semantic node."""

    name: str
    implementation: str
    compute: str
    source: SourceLocation
    allocation: JobAllocation | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize the transformation."""
        return {
            "name": self.name,
            "implementation": self.implementation,
            "compute": self.compute,
            "source": self.source.to_dict(),
            "allocation": self.allocation.to_dict() if self.allocation else None,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        """Deserialize a transformation."""
        source = _mapping(value["source"])
        return cls(
            name=str(value["name"]),
            implementation=str(value["implementation"]),
            compute=str(value["compute"]),
            source=SourceLocation(str(source["path"]), int(source["line"])),
            allocation=(
                JobAllocation.from_dict(_mapping(value["allocation"]))
                if value.get("allocation")
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class DerivedContext:
    """Plain-language content generated from mechanical evidence."""

    text: str
    generator: str
    derived: bool = True

    def to_dict(self) -> dict[str, object]:
        """Serialize the derived context with an explicit provenance marker."""
        return {
            "text": self.text,
            "generator": self.generator,
            "derived": self.derived,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        """Deserialize derived context."""
        return cls(
            text=str(value["text"]),
            generator=str(value["generator"]),
            derived=bool(value.get("derived", True)),
        )


@dataclass(frozen=True, slots=True)
class LineageNode:
    """One versioned job or dataset in the intended graph."""

    identifier: CanonicalIdentifier
    description: str | None = None
    version: str | None = None
    fields: tuple[DatasetField, ...] = ()
    locations: tuple[DatasetLocation, ...] = ()
    transformations: tuple[Transformation, ...] = ()
    sources: tuple[SourceLocation, ...] = ()
    owners: tuple[str, ...] = ()
    context: DerivedContext | None = None
    attributes: tuple[tuple[str, str], ...] = ()

    @property
    def node_id(self) -> str:
        """Return the canonical node identifier."""
        return self.identifier.value

    @property
    def content_hash(self) -> str:
        """Return a deterministic hash used for graph diffs."""
        return _content_hash(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        """Serialize the node into the stored graph format."""
        return {
            **self.identifier.to_dict(),
            "description": self.description,
            "version": self.version,
            "fields": [field.to_dict() for field in self.fields],
            "locations": [location.to_dict() for location in self.locations],
            "transformations": [
                transformation.to_dict() for transformation in self.transformations
            ],
            "sources": [source.to_dict() for source in self.sources],
            "owners": list(self.owners),
            "context": self.context.to_dict() if self.context else None,
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        """Deserialize a stored lineage node."""
        return cls(
            identifier=CanonicalIdentifier(
                NodeKind(str(value["kind"])),
                str(value["namespace"]),
                str(value["name"]),
            ),
            description=_optional_string(value.get("description")),
            version=_optional_string(value.get("version")),
            fields=tuple(
                DatasetField.from_dict(_mapping(item))
                for item in _sequence(value.get("fields"))
            ),
            locations=tuple(
                DatasetLocation.from_dict(_mapping(item))
                for item in _sequence(value.get("locations"))
            ),
            transformations=tuple(
                Transformation.from_dict(_mapping(item))
                for item in _sequence(value.get("transformations"))
            ),
            sources=tuple(
                SourceLocation(
                    str(_mapping(item)["path"]),
                    int(_mapping(item)["line"]),
                )
                for item in _sequence(value.get("sources"))
            ),
            owners=tuple(str(item) for item in _sequence(value.get("owners"))),
            context=(
                DerivedContext.from_dict(_mapping(value["context"]))
                if value.get("context")
                else None
            ),
            attributes=tuple(
                sorted(
                    (str(key), str(item))
                    for key, item in _mapping(value.get("attributes")).items()
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class LineageEdge:
    """One directed relationship between canonical lineage nodes."""

    source_id: str
    target_id: str
    kind: EdgeKind
    attributes: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        """Reject malformed graph edges."""
        if not self.source_id.strip() or not self.target_id.strip():
            raise LineageValidationError.empty_edge_endpoint()

    @property
    def edge_id(self) -> str:
        """Return a stable edge identifier."""
        return f"{self.kind.value}:{self.source_id}->{self.target_id}"

    @property
    def content_hash(self) -> str:
        """Return a deterministic hash used for graph diffs."""
        return _content_hash(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        """Serialize the edge."""
        return {
            "id": self.edge_id,
            "source": self.source_id,
            "target": self.target_id,
            "kind": self.kind.value,
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        """Deserialize a stored edge."""
        return cls(
            source_id=str(value["source"]),
            target_id=str(value["target"]),
            kind=EdgeKind(str(value["kind"])),
            attributes=tuple(
                sorted(
                    (str(key), str(item))
                    for key, item in _mapping(value.get("attributes")).items()
                )
            ),
        )


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _sequence(value: object) -> list[object]:
    return list(value) if isinstance(value, list | tuple) else []


def _optional_string(value: object) -> str | None:
    return str(value) if value is not None else None


def _content_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
