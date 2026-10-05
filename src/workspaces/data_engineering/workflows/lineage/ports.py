"""Outbound persistence contract for versioned lineage graphs."""

from __future__ import annotations

from typing import Protocol

from workspaces.data_engineering.workflows.lineage.graph_models import (
    GraphDiff,
    LineageGraph,
)


class LineageQuerySource(Protocol):
    """Read immutable graph versions for search and traversal."""

    def latest(self, repository: str, profile: str) -> LineageGraph | None:
        """Return the latest stored graph for a repository extraction profile."""
        ...

    def history(
        self,
        repository: str,
        profile: str,
        limit: int,
    ) -> tuple[LineageGraph, ...]:
        """Return graph versions newest first."""
        ...


class LineageStore(Protocol):
    """Persist and retrieve repository lineage graph versions."""

    def latest(self, repository: str, profile: str) -> LineageGraph | None:
        """Return the latest stored graph for a repository extraction profile."""
        ...

    def save(self, graph: LineageGraph, diff: GraphDiff) -> bool:
        """Persist a graph version and return whether it was newly inserted."""
        ...
