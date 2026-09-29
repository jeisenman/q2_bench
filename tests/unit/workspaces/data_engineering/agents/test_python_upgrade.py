from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dependency_intelligence import PackageCompatibility, PackageRelease
from workflow_harness import (
    WorkflowAuthorizationError,
    WorkflowRequest,
    WorkflowRunner,
)
from workspaces.data_engineering.agents.python_upgrade import (
    ProjectDependency,
    PythonProjectInventory,
    PythonUpgradeInput,
    PythonUpgradePlanError,
    PythonUpgradeWorkflow,
)

RELEASE_LOOKAHEAD = 50


class FakeProjectSource:
    def __init__(self, inventory: PythonProjectInventory) -> None:
        self.inventory = inventory
        self.applied: list[tuple[Path, str, str]] = []

    async def inspect(self, project_root: Path) -> PythonProjectInventory:
        assert project_root == self.inventory.project_root
        return self.inventory

    async def apply_requires_python(
        self,
        project_root: Path,
        target_python: str,
        expected_fingerprint: str,
    ) -> tuple[str, ...]:
        self.applied.append((project_root, target_python, expected_fingerprint))
        return ("pyproject.toml", "uv.lock")


class FakeDependencySource:
    def __init__(
        self,
        *,
        compatibility: bool | None,
        releases: tuple[PackageRelease, ...],
    ) -> None:
        self.compatibility = compatibility
        self.releases = releases

    async def list_releases(
        self,
        package: str,
        *,
        include_prereleases: bool = False,
        limit: int = 50,
    ) -> tuple[PackageRelease, ...]:
        assert package == "example"
        assert include_prereleases is False
        assert limit == RELEASE_LOOKAHEAD
        return self.releases

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
            self.compatibility,
        )

    async def list_changes(self, package, from_version, to_version):
        raise AssertionError((package, from_version, to_version))


def _inventory(tmp_path: Path) -> PythonProjectInventory:
    return PythonProjectInventory(
        project_root=tmp_path,
        requires_python=">=3.11",
        dependencies=(ProjectDependency("example", "example>=1", "1.0.0"),),
        fingerprint="fingerprint",
    )


def test_python_upgrade_workflow_builds_read_only_plan(tmp_path: Path) -> None:
    workflow = PythonUpgradeWorkflow(
        FakeProjectSource(_inventory(tmp_path)),
        FakeDependencySource(
            compatibility=True,
            releases=(PackageRelease("example", "2.0.0", ">=3.12"),),
        ),
    )

    result = asyncio.run(
        WorkflowRunner().run(
            workflow,
            WorkflowRequest(
                PythonUpgradeInput(tmp_path, "3.12"),
                correlation_id="upgrade-1",
            ),
        )
    )

    assert result.completed_stages == ("inventory", "analyze", "plan")
    assert result.output.plan.blockers == ()
    assert result.output.plan.unknowns == ()
    assert result.output.applied is False


def test_python_upgrade_workflow_requires_stage_authorization(
    tmp_path: Path,
) -> None:
    workflow = PythonUpgradeWorkflow(
        FakeProjectSource(_inventory(tmp_path)),
        FakeDependencySource(
            compatibility=True,
            releases=(PackageRelease("example", "1.0.0", ">=3.11"),),
        ),
    )

    with pytest.raises(WorkflowAuthorizationError, match="explicit authorization"):
        asyncio.run(
            WorkflowRunner().run(
                workflow,
                WorkflowRequest(
                    PythonUpgradeInput(
                        tmp_path,
                        "3.12",
                        apply_changes=True,
                        expected_fingerprint="fingerprint",
                    ),
                    correlation_id="upgrade-2",
                ),
            )
        )


def test_python_upgrade_workflow_applies_current_safe_plan(tmp_path: Path) -> None:
    project = FakeProjectSource(_inventory(tmp_path))
    workflow = PythonUpgradeWorkflow(
        project,
        FakeDependencySource(
            compatibility=True,
            releases=(PackageRelease("example", "1.0.0", ">=3.11"),),
        ),
    )

    result = asyncio.run(
        WorkflowRunner().run(
            workflow,
            WorkflowRequest(
                PythonUpgradeInput(
                    tmp_path,
                    "3.12",
                    apply_changes=True,
                    expected_fingerprint="fingerprint",
                ),
                correlation_id="upgrade-3",
                authorized_stages=frozenset({"apply"}),
            ),
        )
    )

    assert result.completed_stages == ("inventory", "analyze", "plan", "apply")
    assert result.output.applied is True
    assert project.applied == [(tmp_path, "3.12", "fingerprint")]


def test_python_upgrade_workflow_rejects_unknown_support_on_apply(
    tmp_path: Path,
) -> None:
    workflow = PythonUpgradeWorkflow(
        FakeProjectSource(_inventory(tmp_path)),
        FakeDependencySource(
            compatibility=None,
            releases=(PackageRelease("example", "2.0.0", None),),
        ),
    )

    with pytest.raises(PythonUpgradePlanError, match="unknown support"):
        asyncio.run(
            WorkflowRunner().run(
                workflow,
                WorkflowRequest(
                    PythonUpgradeInput(
                        tmp_path,
                        "3.12",
                        apply_changes=True,
                        expected_fingerprint="fingerprint",
                    ),
                    correlation_id="upgrade-4",
                    authorized_stages=frozenset({"apply"}),
                ),
            )
        )


def test_python_upgrade_input_rejects_excessive_parallelism(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="between 1 and 5"):
        PythonUpgradeInput(tmp_path, "3.12", max_parallel=6)


@pytest.mark.parametrize(
    ("compatibility", "releases", "message"),
    [
        (False, (), "blocked packages"),
        (
            False,
            (PackageRelease("example", "2.0.0", ">=3.12"),),
            "dependency updates",
        ),
    ],
)
def test_python_upgrade_workflow_rejects_unready_apply_plans(
    tmp_path: Path,
    compatibility: bool,
    releases: tuple[PackageRelease, ...],
    message: str,
) -> None:
    workflow = PythonUpgradeWorkflow(
        FakeProjectSource(_inventory(tmp_path)),
        FakeDependencySource(
            compatibility=compatibility,
            releases=releases,
        ),
    )

    with pytest.raises(PythonUpgradePlanError, match=message):
        asyncio.run(
            WorkflowRunner().run(
                workflow,
                WorkflowRequest(
                    PythonUpgradeInput(
                        tmp_path,
                        "3.12",
                        apply_changes=True,
                        expected_fingerprint="fingerprint",
                    ),
                    correlation_id="upgrade-unready",
                    authorized_stages=frozenset({"apply"}),
                ),
            )
        )


def test_python_upgrade_workflow_rejects_stale_plan(tmp_path: Path) -> None:
    workflow = PythonUpgradeWorkflow(
        FakeProjectSource(_inventory(tmp_path)),
        FakeDependencySource(
            compatibility=True,
            releases=(PackageRelease("example", "1.0.0", ">=3.11"),),
        ),
    )

    with pytest.raises(PythonUpgradePlanError, match="changed after planning"):
        asyncio.run(
            WorkflowRunner().run(
                workflow,
                WorkflowRequest(
                    PythonUpgradeInput(
                        tmp_path,
                        "3.12",
                        apply_changes=True,
                        expected_fingerprint="stale",
                    ),
                    correlation_id="upgrade-stale",
                    authorized_stages=frozenset({"apply"}),
                ),
            )
        )


def test_python_upgrade_workflow_marks_unlocked_dependency_unknown(
    tmp_path: Path,
) -> None:
    inventory = PythonProjectInventory(
        project_root=tmp_path,
        requires_python=">=3.11",
        dependencies=(ProjectDependency("example", "example>=1", None),),
        fingerprint="fingerprint",
    )
    workflow = PythonUpgradeWorkflow(
        FakeProjectSource(inventory),
        FakeDependencySource(
            compatibility=True,
            releases=(PackageRelease("example", "2.0.0", ">=3.12"),),
        ),
    )

    result = asyncio.run(
        WorkflowRunner().run(
            workflow,
            WorkflowRequest(
                PythonUpgradeInput(tmp_path, "3.12"),
                correlation_id="upgrade-unlocked",
            ),
        )
    )

    assert result.output.plan.unknowns == ("example",)
    assert result.output.plan.assessments[0].recommended_version == "2.0.0"
