"""Immutable package-release and compatibility contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

MAX_CHANGE_MARKERS = 20


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        message = f"{field_name} must not be empty"
        raise ValueError(message)


@dataclass(frozen=True, slots=True)
class PackageRelease:
    """Describe one package release and reported change markers."""

    package: str
    version: str
    requires_python: str | None = None
    yanked: bool = False
    published_at: datetime | None = None
    change_markers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate package identity and bounded marker content."""
        _require_text(self.package, "package")
        _require_text(self.version, "version")
        if self.requires_python is not None:
            _require_text(self.requires_python, "requires_python")
        if self.published_at is not None and self.published_at.tzinfo is None:
            message = "published_at must be timezone-aware"
            raise ValueError(message)
        if len(self.change_markers) > MAX_CHANGE_MARKERS:
            message = "change_markers must contain at most 20 entries"
            raise ValueError(message)


@dataclass(frozen=True, slots=True)
class PackageCompatibility:
    """Report whether one release declares support for a Python version."""

    package: str
    version: str
    python_version: str
    requires_python: str | None
    compatible: bool | None

    def __post_init__(self) -> None:
        """Validate compatibility identity fields."""
        _require_text(self.package, "package")
        _require_text(self.version, "version")
        _require_text(self.python_version, "python_version")


@dataclass(frozen=True, slots=True)
class DependencyChangeReport:
    """Return releases and reported change markers across one version range."""

    package: str
    from_version: str
    to_version: str
    releases: tuple[PackageRelease, ...]

    def __post_init__(self) -> None:
        """Validate report identity and package consistency."""
        _require_text(self.package, "package")
        _require_text(self.from_version, "from_version")
        _require_text(self.to_version, "to_version")
        if any(release.package != self.package for release in self.releases):
            message = "dependency change releases must match the report package"
            raise ValueError(message)
