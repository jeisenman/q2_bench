"""Read package metadata and reported change markers from PyPI JSON."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Protocol
from urllib.parse import quote
from urllib.request import Request, urlopen

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from dependency_intelligence import (
    DependencyChangeReport,
    PackageCompatibility,
    PackageRelease,
)

MAX_CHANGE_RELEASES = 20
MAX_RELEASE_LIMIT = 200
MARKER_LIMIT = 20
MARKER_LENGTH = 500
_CHANGE_TERMS = (
    "breaking",
    "removed",
    "removal",
    "deprecated",
    "drop support",
    "requires python",
    "incompatible",
)


class PyPiIntelligenceError(RuntimeError):
    """Raised when PyPI metadata is unavailable or malformed."""

    @classmethod
    def invalid_response(cls) -> PyPiIntelligenceError:
        """Return an error for a non-object JSON response."""
        return cls("PyPI JSON response must be an object")

    @classmethod
    def missing_info(cls) -> PyPiIntelligenceError:
        """Return an error for missing project metadata."""
        return cls("PyPI JSON response is missing project info")

    @classmethod
    def narrow_range(cls) -> PyPiIntelligenceError:
        """Return an error for an excessively broad change request."""
        return cls("dependency change range exceeds 20 releases; narrow the range")


class PyPiTransport(Protocol):
    """Small injectable boundary for PyPI JSON reads."""

    def get(self, url: str) -> object:
        """Return decoded JSON from one URL."""
        ...


class UrllibPyPiTransport:
    """Read PyPI JSON with the Python standard library."""

    def get(self, url: str) -> object:
        """Execute one bounded JSON request."""
        request = Request(url, headers={"Accept": "application/json"})
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read())


class PyPiDependencyIntelligenceSource:
    """Provide deterministic package intelligence from PyPI metadata."""

    def __init__(self, transport: PyPiTransport | None = None) -> None:
        """Initialize with an optional test transport."""
        self._transport = transport or UrllibPyPiTransport()

    async def list_releases(
        self,
        package: str,
        *,
        include_prereleases: bool = False,
        limit: int = 50,
    ) -> tuple[PackageRelease, ...]:
        """Return newest releases using PEP 440 ordering."""
        if limit < 1 or limit > MAX_RELEASE_LIMIT:
            message = "release limit must be between 1 and 200"
            raise ValueError(message)
        payload = await self._project(package)
        releases = payload.get("releases")
        if not isinstance(releases, Mapping):
            raise PyPiIntelligenceError.invalid_response()
        values = []
        for version_text, files in releases.items():
            try:
                version = Version(str(version_text))
            except InvalidVersion:
                continue
            if version.is_prerelease and not include_prereleases:
                continue
            values.append(_release(package, str(version_text), files))
        return tuple(
            sorted(values, key=lambda item: Version(item.version), reverse=True)[:limit]
        )

    async def check_compatibility(
        self,
        package: str,
        version: str,
        python_version: str,
    ) -> PackageCompatibility:
        """Evaluate the release's declared Requires-Python value."""
        payload = await self._release(package, version)
        info = _info(payload)
        requires_python = info.get("requires_python")
        if requires_python is not None and not isinstance(requires_python, str):
            raise PyPiIntelligenceError.missing_info()
        compatible = _compatible(requires_python, python_version)
        return PackageCompatibility(
            package=package,
            version=version,
            python_version=python_version,
            requires_python=requires_python,
            compatible=compatible,
        )

    async def list_changes(
        self,
        package: str,
        from_version: str,
        to_version: str,
    ) -> DependencyChangeReport:
        """Return release descriptions containing reported change markers."""
        lower = Version(from_version)
        upper = Version(to_version)
        if upper <= lower:
            message = "to_version must be later than from_version"
            raise ValueError(message)
        releases = await self.list_releases(
            package,
            include_prereleases=True,
            limit=MAX_RELEASE_LIMIT,
        )
        selected = tuple(
            release
            for release in reversed(releases)
            if lower < Version(release.version) <= upper
        )
        if len(selected) > MAX_CHANGE_RELEASES:
            raise PyPiIntelligenceError.narrow_range()
        detailed = await asyncio.gather(
            *(self._release_with_markers(package, release) for release in selected)
        )
        return DependencyChangeReport(
            package,
            from_version,
            to_version,
            tuple(detailed),
        )

    async def _release_with_markers(
        self,
        package: str,
        release: PackageRelease,
    ) -> PackageRelease:
        payload = await self._release(package, release.version)
        info = _info(payload)
        description = info.get("description", "")
        markers = _markers(description if isinstance(description, str) else "")
        requires_python = info.get("requires_python")
        return PackageRelease(
            package=release.package,
            version=release.version,
            requires_python=(
                requires_python if isinstance(requires_python, str) else None
            ),
            yanked=release.yanked,
            published_at=release.published_at,
            change_markers=markers,
        )

    async def _project(self, package: str) -> Mapping[str, object]:
        _require_package(package)
        payload = await asyncio.to_thread(
            self._transport.get,
            f"https://pypi.org/pypi/{quote(package, safe='')}/json",
        )
        if not isinstance(payload, Mapping):
            raise PyPiIntelligenceError.invalid_response()
        return payload

    async def _release(self, package: str, version: str) -> Mapping[str, object]:
        _require_package(package)
        payload = await asyncio.to_thread(
            self._transport.get,
            (
                f"https://pypi.org/pypi/{quote(package, safe='')}/"
                f"{quote(version, safe='')}/json"
            ),
        )
        if not isinstance(payload, Mapping):
            raise PyPiIntelligenceError.invalid_response()
        return payload


def _info(payload: Mapping[str, object]) -> Mapping[str, object]:
    info = payload.get("info")
    if not isinstance(info, Mapping):
        raise PyPiIntelligenceError.missing_info()
    return info


def _release(package: str, version: str, files: object) -> PackageRelease:
    uploads = files if isinstance(files, list) else []
    records = tuple(item for item in uploads if isinstance(item, Mapping))
    published = next(
        (
            _datetime(value)
            for item in records
            if (value := item.get("upload_time_iso_8601")) is not None
        ),
        None,
    )
    yanked = bool(records) and all(bool(item.get("yanked")) for item in records)
    requires_python = next(
        (
            value
            for item in records
            if isinstance((value := item.get("requires_python")), str) and value
        ),
        None,
    )
    return PackageRelease(
        package=package,
        version=version,
        requires_python=requires_python,
        yanked=yanked,
        published_at=published,
    )


def _compatible(requires_python: str | None, python_version: str) -> bool | None:
    if requires_python is None or not requires_python.strip():
        return None
    try:
        return SpecifierSet(requires_python).contains(
            Version(python_version),
            prereleases=True,
        )
    except (InvalidSpecifier, InvalidVersion) as error:
        message = "invalid Python compatibility metadata"
        raise PyPiIntelligenceError(message) from error


def _markers(description: str) -> tuple[str, ...]:
    markers = []
    for line in description.splitlines():
        normalized = line.strip().lstrip("#*- ").strip()
        if normalized and any(term in normalized.lower() for term in _CHANGE_TERMS):
            markers.append(normalized[:MARKER_LENGTH])
        if len(markers) == MARKER_LIMIT:
            break
    return tuple(markers)


def _datetime(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _require_package(package: str) -> None:
    if not package.strip():
        message = "package must not be empty"
        raise ValueError(message)
