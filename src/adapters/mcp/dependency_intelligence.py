"""Dependency intelligence source backed by read-only MCP tools."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from adapters.mcp.client import McpToolCaller
from dependency_intelligence import (
    DependencyChangeReport,
    PackageCompatibility,
    PackageRelease,
)


class DependencyIntelligenceMcpError(RuntimeError):
    """Raised when dependency-intelligence MCP data is malformed."""

    @classmethod
    def invalid_releases(cls) -> DependencyIntelligenceMcpError:
        """Return an error for a malformed release collection."""
        return cls("dependency intelligence MCP releases must be a list of objects")

    @classmethod
    def invalid_release(cls) -> DependencyIntelligenceMcpError:
        """Return an error for malformed release metadata."""
        return cls("dependency intelligence MCP release metadata is invalid")

    @classmethod
    def invalid_compatibility(cls) -> DependencyIntelligenceMcpError:
        """Return an error for malformed compatibility metadata."""
        return cls("dependency intelligence MCP compatibility metadata is invalid")


class DependencyIntelligenceMcpSource:
    """Implement dependency intelligence through a dedicated MCP server."""

    def __init__(self, caller: McpToolCaller) -> None:
        """Initialize with an injected MCP caller."""
        self._caller = caller

    async def list_releases(
        self,
        package: str,
        *,
        include_prereleases: bool = False,
        limit: int = 50,
    ) -> tuple[PackageRelease, ...]:
        """Return newest releases through the package capability."""
        result = await self._caller.call_tool(
            "list_package_releases",
            {
                "package": package,
                "include_prereleases": include_prereleases,
                "limit": limit,
            },
        )
        releases = result.get("releases")
        if not isinstance(releases, list) or not all(
            isinstance(release, Mapping) for release in releases
        ):
            raise DependencyIntelligenceMcpError.invalid_releases()
        return tuple(package_release_from_payload(release) for release in releases)

    async def check_compatibility(
        self,
        package: str,
        version: str,
        python_version: str,
    ) -> PackageCompatibility:
        """Evaluate declared Python support through MCP."""
        result = await self._caller.call_tool(
            "check_python_compatibility",
            {
                "package": package,
                "version": version,
                "python_version": python_version,
            },
        )
        return package_compatibility_from_payload(result)

    async def list_changes(
        self,
        package: str,
        from_version: str,
        to_version: str,
    ) -> DependencyChangeReport:
        """Return bounded reported change markers through MCP."""
        result = await self._caller.call_tool(
            "list_dependency_changes",
            {
                "package": package,
                "from_version": from_version,
                "to_version": to_version,
            },
        )
        releases = result.get("releases")
        if not isinstance(releases, list) or not all(
            isinstance(release, Mapping) for release in releases
        ):
            raise DependencyIntelligenceMcpError.invalid_releases()
        report_package = _required_string(result, "package")
        return DependencyChangeReport(
            package=report_package,
            from_version=_required_string(result, "from_version"),
            to_version=_required_string(result, "to_version"),
            releases=tuple(
                package_release_from_payload(release) for release in releases
            ),
        )


def package_release_payload(release: PackageRelease) -> dict[str, object]:
    """Serialize one package release into a bounded MCP object."""
    return {
        "package": release.package,
        "version": release.version,
        "requires_python": release.requires_python,
        "yanked": release.yanked,
        "published_at": (
            release.published_at.isoformat()
            if release.published_at is not None
            else None
        ),
        "change_markers": list(release.change_markers),
    }


def package_release_from_payload(payload: Mapping[str, object]) -> PackageRelease:
    """Parse one package release from a structured MCP object."""
    requires_python = payload.get("requires_python")
    published_at = payload.get("published_at")
    yanked = payload.get("yanked", False)
    markers = payload.get("change_markers", [])
    if requires_python is not None and not isinstance(requires_python, str):
        raise DependencyIntelligenceMcpError.invalid_release()
    if published_at is not None and not isinstance(published_at, str):
        raise DependencyIntelligenceMcpError.invalid_release()
    if not isinstance(yanked, bool):
        raise DependencyIntelligenceMcpError.invalid_release()
    if not isinstance(markers, list) or not all(
        isinstance(marker, str) for marker in markers
    ):
        raise DependencyIntelligenceMcpError.invalid_release()
    try:
        parsed_published_at = (
            datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            if published_at is not None
            else None
        )
    except ValueError as error:
        raise DependencyIntelligenceMcpError.invalid_release() from error
    return PackageRelease(
        package=_required_string(payload, "package"),
        version=_required_string(payload, "version"),
        requires_python=requires_python,
        yanked=yanked,
        published_at=parsed_published_at,
        change_markers=tuple(markers),
    )


def package_compatibility_payload(
    compatibility: PackageCompatibility,
) -> dict[str, object]:
    """Serialize one compatibility result into a bounded MCP object."""
    return {
        "package": compatibility.package,
        "version": compatibility.version,
        "python_version": compatibility.python_version,
        "requires_python": compatibility.requires_python,
        "compatible": compatibility.compatible,
    }


def package_compatibility_from_payload(
    payload: Mapping[str, object],
) -> PackageCompatibility:
    """Parse one compatibility result from a structured MCP object."""
    requires_python = payload.get("requires_python")
    compatible = payload.get("compatible")
    if requires_python is not None and not isinstance(requires_python, str):
        raise DependencyIntelligenceMcpError.invalid_compatibility()
    if compatible is not None and not isinstance(compatible, bool):
        raise DependencyIntelligenceMcpError.invalid_compatibility()
    return PackageCompatibility(
        package=_required_string(payload, "package"),
        version=_required_string(payload, "version"),
        python_version=_required_string(payload, "python_version"),
        requires_python=requires_python,
        compatible=compatible,
    )


def _required_string(payload: Mapping[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise DependencyIntelligenceMcpError.invalid_release()
    return value
