"""Provider-neutral dependency intelligence boundary."""

from __future__ import annotations

from typing import Protocol

from dependency_intelligence.models import (
    DependencyChangeReport,
    PackageCompatibility,
    PackageRelease,
)


class DependencyIntelligenceSource(Protocol):
    """Read package releases, compatibility, and reported changes."""

    async def list_releases(
        self,
        package: str,
        *,
        include_prereleases: bool = False,
        limit: int = 50,
    ) -> tuple[PackageRelease, ...]:
        """Return the newest package releases."""
        ...

    async def check_compatibility(
        self,
        package: str,
        version: str,
        python_version: str,
    ) -> PackageCompatibility:
        """Evaluate declared Requires-Python compatibility."""
        ...

    async def list_changes(
        self,
        package: str,
        from_version: str,
        to_version: str,
    ) -> DependencyChangeReport:
        """Return releases and reported breaking-change markers in a range."""
        ...
