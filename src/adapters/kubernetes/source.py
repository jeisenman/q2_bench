"""Run the read-only production cluster-health script."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from workspaces.data_engineering.agents.prod_support.cluster_health import (
    RegionalClusterHealth,
)
from workspaces.data_engineering.agents.prod_support.models import Region


class ClusterHealthScriptError(RuntimeError):
    """Raised when the cluster-health script returns invalid evidence."""

    @classmethod
    def invalid_output(cls) -> ClusterHealthScriptError:
        """Return an error for malformed script output."""
        return cls("cluster-health script output must be a JSON object")

    @classmethod
    def region_mismatch(
        cls,
        expected: Region,
        actual: object,
    ) -> ClusterHealthScriptError:
        """Return an error for evidence from the wrong region."""
        return cls(
            f"cluster-health script returned region {actual!r}; "
            f"expected {expected.value!r}"
        )


@dataclass(frozen=True, slots=True)
class ClusterHealthScriptSource:
    """Invoke a repository-owned read-only health script per region."""

    script_path: Path
    python_executable: str = sys.executable

    @classmethod
    def from_repository(cls) -> ClusterHealthScriptSource:
        """Build the source for this repository checkout."""
        root = Path(__file__).resolve().parents[3]
        return cls(root / "scripts" / "check_prod_cluster_health.py")

    async def inspect_health(self, region: Region) -> RegionalClusterHealth:
        """Return script-formatted pod, restart, and KEDA health."""
        result = await asyncio.to_thread(
            subprocess.run,
            (
                self.python_executable,
                str(self.script_path),
                "--region",
                region.value,
            ),
            check=True,
            capture_output=True,
            text=True,
        )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise ClusterHealthScriptError.invalid_output() from error
        if not isinstance(payload, dict):
            raise ClusterHealthScriptError.invalid_output()
        if payload.get("region") != region.value:
            raise ClusterHealthScriptError.region_mismatch(
                region,
                payload.get("region"),
            )
        return RegionalClusterHealth(
            region=region,
            observed_at=datetime.fromisoformat(str(payload["observed_at"])),
            pods_healthy=bool(payload["pods_healthy"]),
            restart_count=int(payload["restart_count"]),
            keda_status=str(payload["keda_status"]),
            symptoms=tuple(str(item) for item in payload.get("symptoms", ())),
            warnings=tuple(str(item) for item in payload.get("warnings", ())),
        )
