"""Typed Python-version upgrade planning and approval-gated mutation."""

from __future__ import annotations

import asyncio

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from dependency_intelligence import DependencyIntelligenceSource, PackageRelease
from workflow_harness import (
    SideEffectPolicy,
    WorkflowCapabilityDefinition,
    WorkflowDefinition,
    WorkflowExecutionContext,
    WorkflowRequest,
    WorkflowStageDefinition,
)
from workspaces.data_engineering.agents.python_upgrade.models import (
    DependencyAssessment,
    DependencyVersionUpdate,
    ProjectDependency,
    PythonProjectInventory,
    PythonUpgradeInput,
    PythonUpgradeOutcome,
    PythonUpgradePlan,
)
from workspaces.data_engineering.agents.python_upgrade.ports import (
    PythonProjectSource,
)

RELEASE_LOOKAHEAD = 50
PYTHON_VERSION_COMPONENTS = 2


class PythonUpgradePlanError(RuntimeError):
    """Raised when a Python upgrade cannot be safely planned or applied."""

    @classmethod
    def invalid_target(cls) -> PythonUpgradePlanError:
        """Return an error for a target that is not a major.minor version."""
        return cls("target_python must be a stable major.minor version such as 3.12")

    @classmethod
    def missing_minimum(cls) -> PythonUpgradePlanError:
        """Return an error for unsupported Requires-Python metadata."""
        return cls("project requires-python must declare a >= major.minor minimum")

    @classmethod
    def not_an_upgrade(cls) -> PythonUpgradePlanError:
        """Return an error when the target does not raise the minimum."""
        return cls("target_python must be newer than the current minimum")

    @classmethod
    def stale_plan(cls) -> PythonUpgradePlanError:
        """Return an error when project state changed since planning."""
        return cls("project files changed after planning; generate a new plan")

    @classmethod
    def blocked_packages(cls, packages: tuple[str, ...]) -> PythonUpgradePlanError:
        """Return an error for dependencies without a compatible release."""
        return cls(
            f"Python upgrade cannot be applied; blocked packages: {', '.join(packages)}"
        )

    @classmethod
    def unknown_packages(cls, packages: tuple[str, ...]) -> PythonUpgradePlanError:
        """Return an error for dependencies with missing support metadata."""
        return cls(
            "Python upgrade cannot be applied; packages with unknown support: "
            f"{', '.join(packages)}"
        )

    @classmethod
    def dependency_updates(
        cls,
        packages: tuple[str, ...],
    ) -> PythonUpgradePlanError:
        """Return an error for dependency updates requiring review."""
        return cls(
            "Python upgrade cannot be applied; dependency updates must be "
            f"reviewed first: {', '.join(packages)}"
        )


class PythonUpgradeWorkflow:
    """Plan a Python minimum-version change and apply only a verified safe plan."""

    def __init__(
        self,
        project_source: PythonProjectSource,
        dependency_source: DependencyIntelligenceSource,
    ) -> None:
        """Initialize with injected project and dependency capabilities."""
        self._project_source = project_source
        self._dependency_source = dependency_source
        self._definition = WorkflowDefinition(
            name="python-upgrade",
            description=(
                "Inventory a uv project, analyze package compatibility, and "
                "optionally apply an approved Python minimum-version update."
            ),
            version="1.0.0",
            capabilities=(
                WorkflowCapabilityDefinition(
                    name="project.read",
                    description="Read pyproject.toml and uv.lock.",
                ),
                WorkflowCapabilityDefinition(
                    name="dependency-intelligence.read",
                    description="Read PyPI release and Requires-Python metadata.",
                ),
                WorkflowCapabilityDefinition(
                    name="project.write",
                    description="Update pyproject.toml and regenerate uv.lock.",
                    side_effect_policy=SideEffectPolicy.APPROVAL_REQUIRED,
                ),
            ),
            stages=(
                WorkflowStageDefinition(
                    name="inventory",
                    description=(
                        "Read direct dependencies and the current Python range."
                    ),
                    capabilities=("project.read",),
                ),
                WorkflowStageDefinition(
                    name="analyze",
                    description="Evaluate locked dependency compatibility.",
                    capabilities=("dependency-intelligence.read",),
                ),
                WorkflowStageDefinition(
                    name="plan",
                    description="Build blockers, unknowns, and required updates.",
                ),
                WorkflowStageDefinition(
                    name="apply",
                    description="Apply a current safe plan and regenerate the lock.",
                    capabilities=("project.write",),
                    side_effect_policy=SideEffectPolicy.APPROVAL_REQUIRED,
                ),
            ),
        )

    @property
    def definition(self) -> WorkflowDefinition:
        """Return immutable Python-upgrade workflow metadata."""
        return self._definition

    async def execute(
        self,
        request: WorkflowRequest[PythonUpgradeInput],
        context: WorkflowExecutionContext,
    ) -> PythonUpgradeOutcome:
        """Run inventory, compatibility analysis, planning, and optional apply."""
        workflow_input = request.input

        async def inventory_project() -> PythonProjectInventory:
            inventory = await self._project_source.inspect(workflow_input.project_root)
            _validate_upgrade(inventory.requires_python, workflow_input.target_python)
            return inventory

        inventory = await context.run_stage("inventory", inventory_project)

        async def analyze_dependencies() -> tuple[DependencyAssessment, ...]:
            return await self._analyze(
                inventory.dependencies,
                workflow_input.target_python,
                workflow_input.max_parallel,
            )

        assessments = await context.run_stage("analyze", analyze_dependencies)

        async def build_plan() -> PythonUpgradePlan:
            return _plan(inventory, workflow_input.target_python, assessments)

        plan = await context.run_stage("plan", build_plan)
        if not workflow_input.apply_changes:
            return PythonUpgradeOutcome(plan)

        async def apply_plan() -> tuple[str, ...]:
            _validate_apply(plan, workflow_input.expected_fingerprint)
            return await self._project_source.apply_requires_python(
                inventory.project_root,
                workflow_input.target_python,
                plan.inventory_fingerprint,
            )

        changed_files = await context.run_stage("apply", apply_plan)
        return PythonUpgradeOutcome(plan, applied=True, changed_files=changed_files)

    async def _analyze(
        self,
        dependencies: tuple[ProjectDependency, ...],
        target_python: str,
        max_parallel: int,
    ) -> tuple[DependencyAssessment, ...]:
        semaphore = asyncio.Semaphore(max_parallel)

        async def assess(dependency: ProjectDependency) -> DependencyAssessment:
            async with semaphore:
                return await self._assess(dependency, target_python)

        return tuple(await asyncio.gather(*(assess(item) for item in dependencies)))

    async def _assess(
        self,
        dependency: ProjectDependency,
        target_python: str,
    ) -> DependencyAssessment:
        releases = await self._dependency_source.list_releases(
            dependency.package,
            limit=RELEASE_LOOKAHEAD,
        )
        recommendation = _recommended_release(
            dependency,
            target_python,
            releases,
        )
        if dependency.locked_version is None:
            return DependencyAssessment(
                package=dependency.package,
                requirement=dependency.requirement,
                current_version=None,
                current_requires_python=None,
                current_compatible=None,
                recommended_version=recommendation,
            )
        compatibility = await self._dependency_source.check_compatibility(
            dependency.package,
            dependency.locked_version,
            target_python,
        )
        return DependencyAssessment(
            package=dependency.package,
            requirement=dependency.requirement,
            current_version=dependency.locked_version,
            current_requires_python=compatibility.requires_python,
            current_compatible=compatibility.compatible,
            recommended_version=(
                dependency.locked_version
                if compatibility.compatible is True
                else recommendation
            ),
        )


def _validate_upgrade(requires_python: str, target_python: str) -> None:
    target = _target_version(target_python)
    current = _minimum_version(requires_python)
    if target <= current:
        raise PythonUpgradePlanError.not_an_upgrade()


def _target_version(target_python: str) -> Version:
    try:
        parsed = Version(target_python)
    except InvalidVersion as error:
        raise PythonUpgradePlanError.invalid_target() from error
    if parsed.is_prerelease or len(parsed.release) != PYTHON_VERSION_COMPONENTS:
        raise PythonUpgradePlanError.invalid_target()
    return parsed


def _minimum_version(requires_python: str) -> Version:
    try:
        specifiers = SpecifierSet(requires_python)
    except InvalidSpecifier as error:
        raise PythonUpgradePlanError.missing_minimum() from error
    minimums = [
        Version(specifier.version)
        for specifier in specifiers
        if specifier.operator == ">="
    ]
    if not minimums:
        raise PythonUpgradePlanError.missing_minimum()
    return max(minimums)


def _recommended_release(
    dependency: ProjectDependency,
    target_python: str,
    releases: tuple[PackageRelease, ...],
) -> str | None:
    try:
        requirement = Requirement(dependency.requirement)
    except InvalidRequirement as error:
        message = f"invalid dependency requirement: {dependency.requirement}"
        raise PythonUpgradePlanError(message) from error
    target = _target_version(target_python)
    for release in releases:
        try:
            version = Version(release.version)
        except InvalidVersion:
            continue
        if release.yanked or not requirement.specifier.contains(version):
            continue
        if _supports_python(release.requires_python, target) is True:
            return release.version
    return None


def _supports_python(requires_python: str | None, target: Version) -> bool | None:
    if requires_python is None or not requires_python.strip():
        return None
    try:
        return SpecifierSet(requires_python).contains(target, prereleases=True)
    except InvalidSpecifier as error:
        message = f"invalid Requires-Python metadata: {requires_python}"
        raise PythonUpgradePlanError(message) from error


def _plan(
    inventory: PythonProjectInventory,
    target_python: str,
    assessments: tuple[DependencyAssessment, ...],
) -> PythonUpgradePlan:
    blockers = tuple(
        sorted(
            item.package
            for item in assessments
            if item.current_compatible is False and item.recommended_version is None
        )
    )
    unknowns = tuple(
        sorted(item.package for item in assessments if item.current_compatible is None)
    )
    updates = tuple(
        DependencyVersionUpdate(
            item.package,
            item.current_version,
            item.recommended_version,
        )
        for item in assessments
        if item.current_compatible is False
        and item.current_version is not None
        and item.recommended_version is not None
        and item.current_version != item.recommended_version
    )
    return PythonUpgradePlan(
        project_root=inventory.project_root,
        current_requires_python=inventory.requires_python,
        target_python=target_python,
        inventory_fingerprint=inventory.fingerprint,
        assessments=assessments,
        blockers=blockers,
        unknowns=unknowns,
        dependency_updates=updates,
    )


def _validate_apply(
    plan: PythonUpgradePlan,
    expected_fingerprint: str | None,
) -> None:
    if expected_fingerprint != plan.inventory_fingerprint:
        raise PythonUpgradePlanError.stale_plan()
    if plan.blockers:
        raise PythonUpgradePlanError.blocked_packages(plan.blockers)
    if plan.unknowns:
        raise PythonUpgradePlanError.unknown_packages(plan.unknowns)
    if plan.dependency_updates:
        raise PythonUpgradePlanError.dependency_updates(
            tuple(update.package for update in plan.dependency_updates)
        )
