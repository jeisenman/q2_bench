from __future__ import annotations

import asyncio

import pytest

from adapters.dependency_intelligence import (
    PyPiDependencyIntelligenceSource,
    PyPiIntelligenceError,
    UrllibPyPiTransport,
)
from adapters.dependency_intelligence import pypi as pypi_module


class FakeTransport:
    def __init__(self, responses: dict[str, object]) -> None:
        self.responses = responses

    def get(self, url: str) -> object:
        return self.responses[url]


def test_pypi_source_orders_releases_and_checks_compatibility() -> None:
    project_url = "https://pypi.org/pypi/example/json"
    release_url = "https://pypi.org/pypi/example/2.0.0/json"
    source = PyPiDependencyIntelligenceSource(
        FakeTransport(
            {
                project_url: {
                    "releases": {
                        "1.0.0": [
                            {
                                "requires_python": ">=3.9",
                                "upload_time_iso_8601": "2026-01-01T00:00:00Z",
                            }
                        ],
                        "2.0.0rc1": [],
                        "2.0.0": [
                            {
                                "requires_python": ">=3.12",
                                "upload_time_iso_8601": "2026-02-01T00:00:00Z",
                            }
                        ],
                    }
                },
                release_url: {
                    "info": {
                        "requires_python": ">=3.12",
                        "description": "Removed the legacy API.",
                    }
                },
            }
        )
    )

    releases = asyncio.run(source.list_releases("example"))
    compatibility = asyncio.run(source.check_compatibility("example", "2.0.0", "3.11"))

    assert [release.version for release in releases] == ["2.0.0", "1.0.0"]
    assert releases[0].published_at is not None
    assert compatibility.compatible is False


def test_pypi_source_extracts_reported_change_markers() -> None:
    project_url = "https://pypi.org/pypi/example/json"
    release_url = "https://pypi.org/pypi/example/2.0.0/json"
    source = PyPiDependencyIntelligenceSource(
        FakeTransport(
            {
                project_url: {"releases": {"1.0.0": [], "2.0.0": []}},
                release_url: {
                    "info": {
                        "requires_python": ">=3.12",
                        "description": (
                            "Routine maintenance.\nBreaking: removed the legacy client."
                        ),
                    }
                },
            }
        )
    )

    report = asyncio.run(source.list_changes("example", "1.0.0", "2.0.0"))

    assert report.releases[0].change_markers == (
        "Breaking: removed the legacy client.",
    )


def test_pypi_source_rejects_overly_broad_change_ranges() -> None:
    releases = {f"1.{minor}.0": [] for minor in range(22)}
    source = PyPiDependencyIntelligenceSource(
        FakeTransport({"https://pypi.org/pypi/example/json": {"releases": releases}})
    )

    with pytest.raises(PyPiIntelligenceError, match="narrow the range"):
        asyncio.run(source.list_changes("example", "1.0.0", "1.21.0"))


def test_pypi_source_handles_prereleases_yanks_and_missing_metadata() -> None:
    project_url = "https://pypi.org/pypi/example/json"
    release_url = "https://pypi.org/pypi/example/2.0.0/json"
    source = PyPiDependencyIntelligenceSource(
        FakeTransport(
            {
                project_url: {
                    "releases": {
                        "invalid": [],
                        "2.0.0rc1": [],
                        "2.0.0": [
                            {
                                "yanked": True,
                                "upload_time_iso_8601": "invalid",
                            }
                        ],
                    }
                },
                release_url: {"info": {"requires_python": None}},
            }
        )
    )

    releases = asyncio.run(source.list_releases("example", include_prereleases=True))
    compatibility = asyncio.run(source.check_compatibility("example", "2.0.0", "3.12"))

    assert [release.version for release in releases] == ["2.0.0", "2.0.0rc1"]
    assert releases[0].yanked is True
    assert releases[0].published_at is None
    assert compatibility.compatible is None


@pytest.mark.parametrize("limit", [0, 201])
def test_pypi_source_rejects_invalid_release_limits(limit: int) -> None:
    source = PyPiDependencyIntelligenceSource(FakeTransport({}))

    with pytest.raises(ValueError, match="between 1 and 200"):
        asyncio.run(source.list_releases("example", limit=limit))


@pytest.mark.parametrize(
    ("responses", "operation", "message"),
    [
        (
            {"https://pypi.org/pypi/example/json": []},
            "list",
            "must be an object",
        ),
        (
            {"https://pypi.org/pypi/example/json": {}},
            "list",
            "must be an object",
        ),
        (
            {"https://pypi.org/pypi/example/1.0.0/json": {}},
            "compatibility",
            "missing project info",
        ),
        (
            {
                "https://pypi.org/pypi/example/1.0.0/json": {
                    "info": {"requires_python": ["invalid"]}
                }
            },
            "compatibility",
            "missing project info",
        ),
        (
            {
                "https://pypi.org/pypi/example/1.0.0/json": {
                    "info": {"requires_python": "not a specifier"}
                }
            },
            "compatibility",
            "invalid Python compatibility",
        ),
    ],
)
def test_pypi_source_rejects_malformed_metadata(
    responses: dict[str, object],
    operation: str,
    message: str,
) -> None:
    source = PyPiDependencyIntelligenceSource(FakeTransport(responses))

    def list_releases() -> None:
        asyncio.run(source.list_releases("example"))

    def check_compatibility() -> None:
        asyncio.run(source.check_compatibility("example", "1.0.0", "3.12"))

    action = list_releases if operation == "list" else check_compatibility

    with pytest.raises(PyPiIntelligenceError, match=message):
        action()


def test_pypi_source_rejects_invalid_ranges_and_blank_packages() -> None:
    source = PyPiDependencyIntelligenceSource(FakeTransport({}))

    with pytest.raises(ValueError, match="later"):
        asyncio.run(source.list_changes("example", "2.0.0", "1.0.0"))
    with pytest.raises(ValueError, match="must not be empty"):
        asyncio.run(source.list_releases(" "))


def test_urllib_transport_decodes_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def read(self) -> bytes:
            return b'{"status": "ready"}'

    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        del request, timeout
        return FakeResponse()

    monkeypatch.setattr(pypi_module, "urlopen", fake_urlopen)

    assert UrllibPyPiTransport().get("https://pypi.org/pypi/example/json") == {
        "status": "ready"
    }
