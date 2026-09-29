from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from dependency_intelligence import (
    DependencyChangeReport,
    PackageCompatibility,
    PackageRelease,
)
from mcp_servers import dependency_intelligence

RELEASE_LIMIT = 10


class FakeSource:
    async def list_releases(self, package, *, include_prereleases=False, limit=50):
        assert package == "example"
        assert include_prereleases is False
        assert limit == RELEASE_LIMIT
        return (
            PackageRelease(
                package,
                "2.0.0",
                ">=3.12",
                published_at=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        )

    async def check_compatibility(self, package, version, python_version):
        return PackageCompatibility(
            package,
            version,
            python_version,
            ">=3.12",
            True,
        )

    async def list_changes(self, package, from_version, to_version):
        return DependencyChangeReport(package, from_version, to_version, ())


def test_dependency_intelligence_server_exposes_read_only_capabilities(
    monkeypatch,
) -> None:
    monkeypatch.setattr(dependency_intelligence, "_source", FakeSource)

    releases = asyncio.run(
        dependency_intelligence.list_package_releases(
            "example",
            False,
            RELEASE_LIMIT,
        )
    )
    compatibility = asyncio.run(
        dependency_intelligence.check_python_compatibility(
            "example",
            "2.0.0",
            "3.12",
        )
    )
    changes = asyncio.run(
        dependency_intelligence.list_dependency_changes(
            "example",
            "1.0.0",
            "2.0.0",
        )
    )

    assert releases["count"] == 1
    assert compatibility["compatible"] is True
    assert changes["releases"] == []
