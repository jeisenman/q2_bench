"""Immutable contracts for Python-upgrade inventory, analysis, and output."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

MAX_PARALLEL_DEPENDENCIES = 5


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        message = f"{field_name} must not be empty"
        raise ValueError(message)


@dataclass(frozen=True, slots=True)
class ProjectDependency:
    """Describe one direct project dependency and its locked version."""

    package: str
    requirement: str
    locked_version: str | None

    def __post_init__(self) -> None:
        """Validate dependency identity."""
        _require_text(self.package, "package")
        _require_text(self.requirement, "requirement")
        if self.locked_version is not None:
            _require_text(self.locked_version, "locked_version")


@dataclass(frozen=True, slots=True)
class PythonProjectInventory:
    """Capture the bounded project state used to produce an upgrade plan."""

    project_root: Path
    requires_python: str
    dependencies: tuple[ProjectDependency, ...]
    fingerprint: str

    def __post_init__(self) -> None:
        """Validate inventory identity and deterministic dependency ordering."""
        _require_text(self.requires_python, "requires_python")
        _require_text(self.fingerprint, "fingerprint")
        packages = tuple(dependency.package for dependency in self.dependencies)
        if packages != tuple(sorted(packages)):
            message = "project dependencies must be sorted by package"
            raise ValueError(message)
        if len(packages) != len(set(packages)):
            message = "project dependencies must be unique"
            raise ValueError(message)


@dataclass(frozen=True, slots=True)
class DependencyAssessment:
    """Describe one dependency's target-Python compatibility."""

    package: str
    requirement: str
    current_version: str | None
    current_requires_python: str | None
    current_compatible: bool | None
    recommended_version: str | None

    def __post_init__(self) -> None:
        """Validate dependency assessment identity."""
        _require_text(self.package, "package")
        _require_text(self.requirement, "requirement")


@dataclass(frozen=True, slots=True)
class DependencyVersionUpdate:
    """Describe a dependency version change required before Python mutation."""

    package: str
    from_version: str
    to_version: str

    def __post_init__(self) -> None:
        """Validate version update identity."""
        _require_text(self.package, "package")
        _require_text(self.from_version, "from_version")
        _require_text(self.to_version, "to_version")


@dataclass(frozen=True, slots=True)
class PythonUpgradePlan:
    """Return a deterministic, stale-plan-protected Python upgrade plan."""

    project_root: Path
    current_requires_python: str
    target_python: str
    inventory_fingerprint: str
    assessments: tuple[DependencyAssessment, ...]
    blockers: tuple[str, ...]
    unknowns: tuple[str, ...]
    dependency_updates: tuple[DependencyVersionUpdate, ...]

    def __post_init__(self) -> None:
        """Validate plan identity and sorted package summaries."""
        _require_text(self.current_requires_python, "current_requires_python")
        _require_text(self.target_python, "target_python")
        _require_text(self.inventory_fingerprint, "inventory_fingerprint")
        for values, name in (
            (self.blockers, "blockers"),
            (self.unknowns, "unknowns"),
        ):
            if values != tuple(sorted(values)):
                message = f"{name} must be sorted"
                raise ValueError(message)


@dataclass(frozen=True, slots=True)
class PythonUpgradeInput:
    """Configure one plan or explicitly authorized apply run."""

    project_root: Path
    target_python: str
    apply_changes: bool = False
    expected_fingerprint: str | None = None
    max_parallel: int = MAX_PARALLEL_DEPENDENCIES

    def __post_init__(self) -> None:
        """Validate target and bounded dependency parallelism."""
        _require_text(self.target_python, "target_python")
        if self.max_parallel < 1 or self.max_parallel > MAX_PARALLEL_DEPENDENCIES:
            message = "max_parallel must be between 1 and 5"
            raise ValueError(message)
        if self.apply_changes and self.expected_fingerprint is None:
            message = "expected_fingerprint is required when applying changes"
            raise ValueError(message)
        if self.expected_fingerprint is not None:
            _require_text(self.expected_fingerprint, "expected_fingerprint")


@dataclass(frozen=True, slots=True)
class PythonUpgradeOutcome:
    """Return the plan and any explicitly authorized workspace changes."""

    plan: PythonUpgradePlan
    applied: bool = False
    changed_files: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Validate apply metadata."""
        if not self.applied and self.changed_files:
            message = "changed_files require an applied outcome"
            raise ValueError(message)
