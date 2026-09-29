from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from adapters.mcp import (
    DependencyIntelligenceMcpError,
    DependencyIntelligenceMcpSource,
    package_compatibility_from_payload,
    package_compatibility_payload,
    package_release_from_payload,
    package_release_payload,
)
from dependency_intelligence import PackageCompatibility, PackageRelease


class FakeCaller:
    async def call_tool(self, name, arguments):
        package = arguments["package"]
        if name == "list_package_releases":
            return {
                "releases": [
                    {
                        "package": package,
                        "version": "2.0.0",
                        "requires_python": ">=3.12",
                        "yanked": False,
                        "published_at": "2026-01-01T00:00:00+00:00",
                        "change_markers": [],
                    }
                ]
            }
        if name == "check_python_compatibility":
            return {
                "package": package,
                "version": arguments["version"],
                "python_version": arguments["python_version"],
                "requires_python": ">=3.12",
                "compatible": True,
            }
        return {
            "package": package,
            "from_version": arguments["from_version"],
            "to_version": arguments["to_version"],
            "releases": [],
        }


def test_dependency_intelligence_mcp_source_implements_all_reads() -> None:
    source = DependencyIntelligenceMcpSource(FakeCaller())

    releases = asyncio.run(source.list_releases("example"))
    compatibility = asyncio.run(source.check_compatibility("example", "2.0.0", "3.12"))
    changes = asyncio.run(source.list_changes("example", "1.0.0", "2.0.0"))

    assert releases[0].version == "2.0.0"
    assert compatibility.compatible is True
    assert changes.package == "example"


def test_dependency_intelligence_payloads_round_trip() -> None:
    release = PackageRelease(
        "example",
        "2.0.0",
        ">=3.12",
        yanked=True,
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        change_markers=("Removed legacy API",),
    )
    compatibility = PackageCompatibility(
        "example",
        "2.0.0",
        "3.12",
        ">=3.12",
        True,
    )

    assert package_release_from_payload(package_release_payload(release)) == release
    assert (
        package_compatibility_from_payload(package_compatibility_payload(compatibility))
        == compatibility
    )
    assert (
        package_release_payload(PackageRelease("example", "1.0.0"))["published_at"]
        is None
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"package": "example", "version": "1", "requires_python": []},
        {"package": "example", "version": "1", "published_at": 1},
        {"package": "example", "version": "1", "yanked": "yes"},
        {"package": "example", "version": "1", "change_markers": "invalid"},
        {"package": "example", "version": "1", "published_at": "invalid"},
        {"package": "", "version": "1"},
    ],
)
def test_dependency_intelligence_rejects_invalid_release_payloads(
    payload: dict[str, object],
) -> None:
    with pytest.raises(DependencyIntelligenceMcpError, match="invalid"):
        package_release_from_payload(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {
            "package": "example",
            "version": "1",
            "python_version": "3.12",
            "requires_python": [],
            "compatible": True,
        },
        {
            "package": "example",
            "version": "1",
            "python_version": "3.12",
            "requires_python": None,
            "compatible": "yes",
        },
    ],
)
def test_dependency_intelligence_rejects_invalid_compatibility_payloads(
    payload: dict[str, object],
) -> None:
    with pytest.raises(DependencyIntelligenceMcpError, match="compatibility"):
        package_compatibility_from_payload(payload)


def test_dependency_intelligence_source_rejects_invalid_release_collections() -> None:
    class InvalidCaller:
        async def call_tool(self, name, arguments):
            del arguments
            if name == "list_package_releases":
                return {"releases": "invalid"}
            return {
                "package": "example",
                "from_version": "1.0.0",
                "to_version": "2.0.0",
                "releases": [1],
            }

    source = DependencyIntelligenceMcpSource(InvalidCaller())

    with pytest.raises(DependencyIntelligenceMcpError, match="list"):
        asyncio.run(source.list_releases("example"))
    with pytest.raises(DependencyIntelligenceMcpError, match="list"):
        asyncio.run(source.list_changes("example", "1.0.0", "2.0.0"))
