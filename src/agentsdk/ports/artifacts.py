"""Artifact persistence port."""

from pathlib import Path
from typing import Protocol


class ArtifactPort(Protocol):
    """Persist and retrieve run artifacts."""

    async def put(self, run_id: str, name: str, source: Path) -> str:
        """Store an artifact and return its provider-neutral URI."""
        ...

    async def get(self, uri: str, destination: Path) -> Path:
        """Materialize an artifact at the requested destination."""
        ...
