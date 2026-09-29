"""Provider-neutral project boundaries for the Python-upgrade workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from workspaces.data_engineering.agents.python_upgrade.models import (
    PythonProjectInventory,
)


class PythonProjectSource(Protocol):
    """Inspect and explicitly update one uv-managed Python project."""

    async def inspect(self, project_root: Path) -> PythonProjectInventory:
        """Return bounded project metadata and a content fingerprint."""
        ...

    async def apply_requires_python(
        self,
        project_root: Path,
        target_python: str,
        expected_fingerprint: str,
    ) -> tuple[str, ...]:
        """Update Requires-Python and regenerate the uv lock atomically."""
        ...
