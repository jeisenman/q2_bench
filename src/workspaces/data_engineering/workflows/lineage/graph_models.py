"""Version, graph, and diff contracts for repository lineage."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Self
from uuid import UUID

from workspaces.data_engineering.workflows.lineage.errors import (
    LineageValidationError,
)
from workspaces.data_engineering.workflows.lineage.models import (
    LineageEdge,
    LineageNode,
    _content_hash,
)

SHA_LENGTH = 40


@dataclass(frozen=True, slots=True)
class RepositoryManifest:
    """Source revision and extraction profile for one graph version."""

    graph_id: UUID
    repository: str
    commit_sha: str
    source_ref: str
    profile: str
    extractor_version: str
    generated_at: datetime

    def __post_init__(self) -> None:
        """Validate immutable revision identity."""
        if len(self.commit_sha) != SHA_LENGTH:
            raise LineageValidationError.invalid_commit_sha()
        if self.generated_at.tzinfo is None:
            raise LineageValidationError.naive_generated_at()

    def to_dict(self) -> dict[str, str]:
        """Serialize the repository manifest."""
        return {
            "graphId": str(self.graph_id),
            "repository": self.repository,
            "commitSha": self.commit_sha,
            "sourceRef": self.source_ref,
            "profile": self.profile,
            "extractorVersion": self.extractor_version,
            "generatedAt": self.generated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        """Deserialize a repository manifest."""
        return cls(
            graph_id=UUID(str(value["graphId"])),
            repository=str(value["repository"]),
            commit_sha=str(value["commitSha"]),
            source_ref=str(value["sourceRef"]),
            profile=str(value["profile"]),
            extractor_version=str(value["extractorVersion"]),
            generated_at=datetime.fromisoformat(str(value["generatedAt"])),
        )


@dataclass(frozen=True, slots=True)
class LineageGraph:
    """A deterministic repository graph using OpenLineage entity identity."""

    manifest: RepositoryManifest
    nodes: tuple[LineageNode, ...]
    edges: tuple[LineageEdge, ...]

    def __post_init__(self) -> None:
        """Require unique nodes and valid edge endpoints."""
        node_ids = [node.node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise LineageValidationError.duplicate_nodes()
        known = set(node_ids)
        missing = sorted(
            {
                endpoint
                for edge in self.edges
                for endpoint in (edge.source_id, edge.target_id)
                if endpoint not in known
            }
        )
        if missing:
            raise LineageValidationError.missing_nodes(missing)

    @property
    def fingerprint(self) -> str:
        """Return a content fingerprint independent of generation time."""
        payload = {
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }
        return _content_hash(payload)

    def to_dict(self) -> dict[str, object]:
        """Serialize the graph for Postgres and review artifacts."""
        return {
            "format": "q2-openlineage-graph/v1",
            "manifest": self.manifest.to_dict(),
            "fingerprint": self.fingerprint,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }

    def to_json(self) -> str:
        """Return deterministic, human-reviewable JSON."""
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        """Deserialize a stored graph."""
        return cls(
            manifest=RepositoryManifest.from_dict(_mapping(value["manifest"])),
            nodes=tuple(
                LineageNode.from_dict(_mapping(item))
                for item in _sequence(value.get("nodes"))
            ),
            edges=tuple(
                LineageEdge.from_dict(_mapping(item))
                for item in _sequence(value.get("edges"))
            ),
        )


@dataclass(frozen=True, slots=True)
class GraphDiff:
    """Structural and content changes between graph versions."""

    previous_graph_id: UUID | None
    added_nodes: tuple[str, ...] = ()
    removed_nodes: tuple[str, ...] = ()
    changed_nodes: tuple[str, ...] = ()
    added_edges: tuple[str, ...] = ()
    removed_edges: tuple[str, ...] = ()
    changed_edges: tuple[str, ...] = ()
    impacted_nodes: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        """Return whether any lineage content changed."""
        return any(
            (
                self.added_nodes,
                self.removed_nodes,
                self.changed_nodes,
                self.added_edges,
                self.removed_edges,
                self.changed_edges,
            )
        )

    def to_dict(self) -> dict[str, object]:
        """Serialize the diff summary."""
        return {
            "previousGraphId": (
                str(self.previous_graph_id) if self.previous_graph_id else None
            ),
            "changed": self.changed,
            "addedNodes": list(self.added_nodes),
            "removedNodes": list(self.removed_nodes),
            "changedNodes": list(self.changed_nodes),
            "addedEdges": list(self.added_edges),
            "removedEdges": list(self.removed_edges),
            "changedEdges": list(self.changed_edges),
            "impactedNodes": list(self.impacted_nodes),
        }


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _sequence(value: object) -> list[object]:
    return list(value) if isinstance(value, list | tuple) else []
