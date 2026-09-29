"""Load and validate data-engineering benchmark manifests."""

from __future__ import annotations

import re
from collections.abc import Iterable
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from workspaces.data_engineering.benchmarks.models import (
    BENCHMARK_STATUSES,
    DEPRECATED,
    Benchmark,
)

SNAKE_CASE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
VERSION = re.compile(r"^\d+\.\d+\.\d+$")
DEPRECATION_FIELDS = frozenset({"since", "reason", "retained_for"})
REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "benchmark_id",
        "display_name",
        "version",
        "group",
        "description",
    }
)


class BenchmarkManifestError(ValueError):
    """Raised when a benchmark manifest is invalid."""

    @classmethod
    def invalid(cls, path: Path, reason: str) -> BenchmarkManifestError:
        """Create an error identifying a manifest and validation reason."""
        return cls(f"{path}: {reason}")


class BenchmarkCatalog:
    """Immutable benchmark catalog indexed by stable benchmark ID."""

    def __init__(self, benchmarks: Iterable[Benchmark]) -> None:
        """Create a catalog and reject duplicate stable identifiers."""
        indexed: dict[str, Benchmark] = {}
        for benchmark in benchmarks:
            if benchmark.benchmark_id in indexed:
                msg = f"Duplicate benchmark ID: {benchmark.benchmark_id}"
                raise BenchmarkManifestError(msg)
            indexed[benchmark.benchmark_id] = benchmark
        self._benchmarks = MappingProxyType(indexed)

    @classmethod
    def load(cls, root: Path) -> BenchmarkCatalog:
        """Load all benchmark manifests beneath a workspace directory."""
        manifests = sorted(root.rglob("manifest.yaml"))
        return cls(_load_manifest(path) for path in manifests)

    def list(self, *, include_deprecated: bool = False) -> tuple[Benchmark, ...]:
        """Return active benchmarks, or every benchmark, by display name."""
        selected = (
            self._benchmarks.values()
            if include_deprecated
            else [item for item in self._benchmarks.values() if item.is_active]
        )
        return tuple(sorted(selected, key=lambda item: item.display_name))

    def list_deprecated(self) -> tuple[Benchmark, ...]:
        """Return retired benchmarks retained as source data for new cases."""
        return tuple(
            sorted(
                (item for item in self._benchmarks.values() if not item.is_active),
                key=lambda item: item.display_name,
            )
        )

    def get(self, benchmark_id: str) -> Benchmark:
        """Return one benchmark or raise an actionable lookup error."""
        try:
            return self._benchmarks[benchmark_id]
        except KeyError as error:
            msg = f"Unknown benchmark ID: {benchmark_id}"
            raise KeyError(msg) from error


def _load_manifest(path: Path) -> Benchmark:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise BenchmarkManifestError.invalid(path, "manifest must be a mapping")
    manifest: dict[str, Any] = raw
    missing = REQUIRED_FIELDS.difference(manifest)
    if missing:
        fields = ", ".join(sorted(missing))
        raise BenchmarkManifestError.invalid(path, f"missing required fields: {fields}")
    if manifest["schema_version"] != 1:
        raise BenchmarkManifestError.invalid(path, "schema_version must be 1")
    group = str(manifest["group"])
    if SNAKE_CASE.fullmatch(group) is None:
        raise BenchmarkManifestError.invalid(path, "group must be snake_case")
    benchmark_id = str(manifest["benchmark_id"])
    if IDENTIFIER.fullmatch(benchmark_id) is None:
        raise BenchmarkManifestError.invalid(path, "benchmark_id is invalid")
    if VERSION.fullmatch(str(manifest["version"])) is None:
        raise BenchmarkManifestError.invalid(path, "version must use MAJOR.MINOR.PATCH")
    display_name = str(manifest["display_name"])
    if not display_name.strip():
        raise BenchmarkManifestError.invalid(path, "display_name must not be empty")
    _validate_status(path, manifest)
    return Benchmark.from_manifest(manifest)


def _validate_status(path: Path, manifest: dict[str, Any]) -> None:
    """Reject unknown statuses and deprecations without a documented reason."""
    status = str(manifest.get("status", "active"))
    if status not in BENCHMARK_STATUSES:
        allowed = ", ".join(sorted(BENCHMARK_STATUSES))
        raise BenchmarkManifestError.invalid(path, f"status must be one of: {allowed}")
    deprecation = manifest.get("deprecated")
    if status != DEPRECATED:
        if deprecation is not None:
            raise BenchmarkManifestError.invalid(
                path, "deprecated block requires status: deprecated"
            )
        return
    if not isinstance(deprecation, dict):
        raise BenchmarkManifestError.invalid(
            path, "status: deprecated requires a deprecated mapping"
        )
    missing = DEPRECATION_FIELDS.difference(deprecation)
    if missing:
        fields = ", ".join(sorted(missing))
        raise BenchmarkManifestError.invalid(
            path, f"deprecated is missing required fields: {fields}"
        )
    for field in sorted(DEPRECATION_FIELDS):
        if not str(deprecation[field]).strip():
            raise BenchmarkManifestError.invalid(
                path, f"deprecated.{field} must not be empty"
            )


def default_catalog() -> BenchmarkCatalog:
    """Load the benchmark catalog bundled with this package."""
    package_root = files("workspaces.data_engineering.benchmarks")
    return BenchmarkCatalog.load(Path(str(package_root)))
