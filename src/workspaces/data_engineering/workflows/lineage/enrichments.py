"""Non-structural source evidence attached to lineage nodes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self


@dataclass(frozen=True, slots=True)
class SourceLocation:
    """Repository source location supporting one lineage assertion."""

    path: str
    line: int

    def to_dict(self) -> dict[str, object]:
        """Serialize the source location."""
        return {"path": self.path, "line": self.line}


@dataclass(frozen=True, slots=True)
class NodeEnrichment:
    """Source-backed detail that does not change structural lineage."""

    category: str
    name: str
    description: str
    sources: tuple[SourceLocation, ...] = ()
    attributes: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Serialize one enrichment record."""
        return {
            "category": self.category,
            "name": self.name,
            "description": self.description,
            "sources": [source.to_dict() for source in self.sources],
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        """Deserialize one enrichment record."""
        return cls(
            category=str(value["category"]),
            name=str(value["name"]),
            description=str(value["description"]),
            sources=tuple(
                SourceLocation(
                    str(_mapping(item)["path"]),
                    int(_mapping(item)["line"]),
                )
                for item in _sequence(value.get("sources"))
            ),
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
