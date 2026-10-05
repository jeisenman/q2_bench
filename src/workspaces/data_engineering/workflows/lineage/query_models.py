"""Typed results for read-only lineage discovery."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from workspaces.data_engineering.workflows.lineage.graph_models import (
    RepositoryManifest,
)
from workspaces.data_engineering.workflows.lineage.models import (
    LineageEdge,
    LineageNode,
)


class TraversalDirection(StrEnum):
    """Supported graph traversal directions."""

    UPSTREAM = "upstream"
    DOWNSTREAM = "downstream"


@dataclass(frozen=True, slots=True)
class LineageSearch:
    """Dataset matches from one immutable graph version."""

    manifest: RepositoryManifest
    nodes: tuple[LineageNode, ...]


@dataclass(frozen=True, slots=True)
class LineageNodeDetails:
    """One full node from an immutable graph version."""

    manifest: RepositoryManifest
    node: LineageNode


@dataclass(frozen=True, slots=True)
class LineageTraversal:
    """Bounded traversal from one node in the latest graph."""

    manifest: RepositoryManifest
    root: LineageNode
    direction: TraversalDirection
    depth: int
    nodes: tuple[LineageNode, ...]
    edges: tuple[LineageEdge, ...]
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class LineageRevision:
    """One source commit where a node was created, changed, or removed."""

    manifest: RepositoryManifest
    change_type: str
    node: LineageNode | None
    content_hash: str | None
