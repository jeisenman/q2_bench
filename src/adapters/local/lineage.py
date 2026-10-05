"""Read a generated lineage graph artifact from local storage."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from workspaces.data_engineering.workflows.lineage.graph_models import LineageGraph

LINEAGE_GRAPH_PATH_ENV = "LINEAGE_GRAPH_PATH"
DEFAULT_LINEAGE_GRAPH_PATH = Path("var/lineage/di-pipelines.json")


class LocalLineageError(RuntimeError):
    """Raised when a local lineage graph cannot be read safely."""

    @classmethod
    def invalid_root(cls) -> LocalLineageError:
        """Create an error for an artifact whose root is not an object."""
        return cls("local lineage graph is not a JSON object")


class JsonLineageGraphSource:
    """Read the latest graph from a generated JSON artifact."""

    def __init__(self, path: Path) -> None:
        """Initialize the source with an explicit artifact path."""
        self._path = path

    @classmethod
    def from_environment(cls) -> JsonLineageGraphSource:
        """Build a source from the configured or default artifact path."""
        raw_path = os.environ.get(LINEAGE_GRAPH_PATH_ENV)
        return cls(Path(raw_path) if raw_path else DEFAULT_LINEAGE_GRAPH_PATH)

    @property
    def path(self) -> Path:
        """Return the configured artifact path."""
        return self._path

    def latest(self, repository: str, profile: str) -> LineageGraph | None:
        """Return the graph when its manifest matches the requested identity."""
        graph = self._load()
        manifest = graph.manifest
        if manifest.repository != repository or manifest.profile != profile:
            return None
        return graph

    def history(
        self,
        repository: str,
        profile: str,
        limit: int,
    ) -> tuple[LineageGraph, ...]:
        """Return the single local graph when it matches the requested identity."""
        if limit < 1:
            message = "lineage history limit must be at least 1"
            raise ValueError(message)
        graph = self.latest(repository, profile)
        return (graph,) if graph is not None else ()

    def _load(self) -> LineageGraph:
        if not self._path.is_file():
            message = (
                f"lineage graph artifact does not exist: {self._path}. "
                "Run 'uv run agentbench lineage-sync --repository "
                "../di-pipelines --source-ref master --dry-run "
                f"--output {self._path}'."
            )
            raise LocalLineageError(message)
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return LineageGraph.from_dict(_mapping(raw))
        except (
            OSError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            message = f"unable to read lineage graph artifact {self._path}: {error}"
            raise LocalLineageError(message) from error


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise LocalLineageError.invalid_root()
    return {str(key): item for key, item in value.items()}
