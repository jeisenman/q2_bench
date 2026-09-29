from __future__ import annotations

import asyncio
from pathlib import Path

from dependency_intelligence import PackageCompatibility, PackageRelease
from mcp_servers import python_upgrade
from workspaces.data_engineering.agents.python_upgrade import (
    ProjectDependency,
    PythonProjectInventory,
    PythonUpgradeWorkflow,
)

RELEASE_LOOKAHEAD = 50


class FakeProjectSource:
    async def inspect(self, project_root: Path) -> PythonProjectInventory:
        return PythonProjectInventory(
            project_root.resolve(),
            ">=3.11",
            (ProjectDependency("example", "example>=1", "1.0.0"),),
            "fingerprint",
        )

    async def apply_requires_python(
        self,
        project_root: Path,
        target_python: str,
        expected_fingerprint: str,
    ) -> tuple[str, ...]:
        del project_root
        assert target_python == "3.12"
        assert expected_fingerprint == "fingerprint"
        return ("pyproject.toml", "uv.lock")


class FakeDependencySource:
    async def list_releases(
        self,
        package: str,
        *,
        include_prereleases: bool = False,
        limit: int = 50,
    ) -> tuple[PackageRelease, ...]:
        assert include_prereleases is False
        assert limit == RELEASE_LOOKAHEAD
        return (PackageRelease(package, "1.0.0", ">=3.11"),)

    async def check_compatibility(
        self,
        package: str,
        version: str,
        python_version: str,
    ) -> PackageCompatibility:
        return PackageCompatibility(
            package,
            version,
            python_version,
            ">=3.11",
            True,
        )

    async def list_changes(self, package, from_version, to_version):
        raise AssertionError((package, from_version, to_version))


def test_python_upgrade_server_plans_and_applies(monkeypatch, tmp_path: Path) -> None:
    workflow = PythonUpgradeWorkflow(FakeProjectSource(), FakeDependencySource())
    monkeypatch.setattr(python_upgrade, "_workflow", lambda: workflow)

    plan = asyncio.run(python_upgrade.plan_python_upgrade(str(tmp_path), "3.12"))
    applied = asyncio.run(
        python_upgrade.apply_python_upgrade(
            str(tmp_path),
            "3.12",
            "fingerprint",
        )
    )

    assert plan["completed_stages"] == ["inventory", "analyze", "plan"]
    assert plan["plan"]["apply_ready"] is True
    assert applied["completed_stages"] == [
        "inventory",
        "analyze",
        "plan",
        "apply",
    ]
    assert applied["changed_files"] == ["pyproject.toml", "uv.lock"]
