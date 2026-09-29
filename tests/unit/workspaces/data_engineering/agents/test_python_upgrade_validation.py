from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dependency_intelligence import PackageCompatibility, PackageRelease
from workflow_harness import WorkflowRequest, WorkflowRunner
from workspaces.data_engineering.agents.python_upgrade import (
    DependencyAssessment,
    DependencyVersionUpdate,
    ProjectDependency,
    PythonProjectInventory,
    PythonUpgradeInput,
    PythonUpgradeOutcome,
    PythonUpgradePlan,
    PythonUpgradePlanError,
    PythonUpgradeWorkflow,
)


class FakeProjectSource:
    def __init__(self, inventory: PythonProjectInventory) -> None:
        self.inventory = inventory

    async def inspect(self, project_root: Path) -> PythonProjectInventory:
        assert project_root == self.inventory.project_root
        return self.inventory

    async def apply_requires_python(
        self,
        project_root: Path,
        target_python: str,
        expected_fingerprint: str,
    ) -> tuple[str, ...]:
        raise AssertionError((project_root, target_python, expected_fingerprint))


class FakeDependencySource:
    def __init__(
        self,
        releases: tuple[PackageRelease, ...],
    ) -> None:
        self.releases = releases

    async def list_releases(
        self,
        package: str,
        *,
        include_prereleases: bool = False,
        limit: int = 50,
    ) -> tuple[PackageRelease, ...]:
        del package, include_prereleases, limit
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
            False,
        )

    async def list_changes(self, package, from_version, to_version):
        raise AssertionError((package, from_version, to_version))


@pytest.mark.parametrize(
    ("requires_python", "target_python", "message"),
    [
        (">=3.11", "invalid", "stable major.minor"),
        (">=3.11", "3.12.1", "stable major.minor"),
        (">=3.11", "3.12rc1", "stable major.minor"),
        (">=3.12", "3.12", "newer"),
        ("~=3.11", "3.12", "must declare"),
        ("not a specifier", "3.12", "must declare"),
    ],
)
def test_python_upgrade_workflow_rejects_invalid_target_ranges(
    tmp_path: Path,
    requires_python: str,
    target_python: str,
    message: str,
) -> None:
    inventory = PythonProjectInventory(
        project_root=tmp_path,
        requires_python=requires_python,
        dependencies=(),
        fingerprint="fingerprint",
    )
    workflow = PythonUpgradeWorkflow(
        FakeProjectSource(inventory),
        FakeDependencySource(()),
    )

    with pytest.raises(PythonUpgradePlanError, match=message):
        asyncio.run(
            WorkflowRunner().run(
                workflow,
                WorkflowRequest(
                    PythonUpgradeInput(tmp_path, target_python),
                    correlation_id="upgrade-invalid",
                ),
            )
        )


def test_python_upgrade_workflow_validates_dependency_metadata(
    tmp_path: Path,
) -> None:
    invalid_requirement = PythonProjectInventory(
        project_root=tmp_path,
        requires_python=">=3.11",
        dependencies=(ProjectDependency("example", "not @", "1.0.0"),),
        fingerprint="fingerprint",
    )
    invalid_release_metadata = PythonProjectInventory(
        project_root=tmp_path,
        requires_python=">=3.11",
        dependencies=(ProjectDependency("example", "example", "1.0.0"),),
        fingerprint="fingerprint",
    )

    with pytest.raises(PythonUpgradePlanError, match="invalid dependency"):
        asyncio.run(
            WorkflowRunner().run(
                PythonUpgradeWorkflow(
                    FakeProjectSource(invalid_requirement),
                    FakeDependencySource(()),
                ),
                WorkflowRequest(
                    PythonUpgradeInput(tmp_path, "3.12"),
                    correlation_id="upgrade-invalid-requirement",
                ),
            )
        )
    with pytest.raises(PythonUpgradePlanError, match="Requires-Python"):
        asyncio.run(
            WorkflowRunner().run(
                PythonUpgradeWorkflow(
                    FakeProjectSource(invalid_release_metadata),
                    FakeDependencySource(
                        (
                            PackageRelease("example", "invalid", ">=3.12"),
                            PackageRelease(
                                "example",
                                "2.0.0",
                                "not a specifier",
                            ),
                        )
                    ),
                ),
                WorkflowRequest(
                    PythonUpgradeInput(tmp_path, "3.12"),
                    correlation_id="upgrade-invalid-metadata",
                ),
            )
        )


def test_python_upgrade_models_reject_invalid_state(tmp_path: Path) -> None:
    dependency = ProjectDependency("a", "a", "1.0.0")
    assessment = DependencyAssessment("a", "a", "1.0.0", ">=3.11", True, "1.0.0")
    plan = PythonUpgradePlan(
        tmp_path,
        ">=3.11",
        "3.12",
        "fingerprint",
        (assessment,),
        (),
        (),
        (),
    )

    with pytest.raises(ValueError, match="locked_version"):
        ProjectDependency("a", "a", " ")
    with pytest.raises(ValueError, match="sorted"):
        PythonProjectInventory(
            tmp_path,
            ">=3.11",
            (ProjectDependency("b", "b", None), dependency),
            "fingerprint",
        )
    with pytest.raises(ValueError, match="unique"):
        PythonProjectInventory(
            tmp_path,
            ">=3.11",
            (dependency, dependency),
            "fingerprint",
        )
    with pytest.raises(ValueError, match="from_version"):
        DependencyVersionUpdate("a", " ", "2.0.0")
    with pytest.raises(ValueError, match="sorted"):
        PythonUpgradePlan(
            tmp_path,
            ">=3.11",
            "3.12",
            "fingerprint",
            (),
            ("b", "a"),
            (),
            (),
        )
    with pytest.raises(ValueError, match="expected_fingerprint"):
        PythonUpgradeInput(tmp_path, "3.12", apply_changes=True)
    with pytest.raises(ValueError, match="between 1 and 5"):
        PythonUpgradeInput(tmp_path, "3.12", max_parallel=0)
    with pytest.raises(ValueError, match="expected_fingerprint"):
        PythonUpgradeInput(tmp_path, "3.12", expected_fingerprint=" ")
    with pytest.raises(ValueError, match="changed_files"):
        PythonUpgradeOutcome(plan, changed_files=("pyproject.toml",))
