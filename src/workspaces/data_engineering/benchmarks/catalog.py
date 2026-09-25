"""Load and validate data-engineering benchmark manifests."""

from __future__ import annotations

import re
from collections.abc import Iterable
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from workspaces.data_engineering.benchmarks.models import Benchmark

SNAKE_CASE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
VERSION = re.compile(r"^\d+\.\d+\.\d+$")
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
        """Load all manifests beneath a benchmark groups directory."""
        manifests = sorted(root.glob("*/**/manifest.yaml"))
        return cls(_load_manifest(path) for path in manifests)

    def list(self) -> tuple[Benchmark, ...]:
        """Return benchmarks sorted by visible display name."""
        return tuple(
            sorted(self._benchmarks.values(), key=lambda item: item.display_name)
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
    return Benchmark.from_manifest(manifest)


def default_catalog() -> BenchmarkCatalog:
    """Load the benchmark catalog bundled with this package."""
    package_root = files("workspaces.data_engineering.benchmarks")
    return BenchmarkCatalog.load(Path(str(package_root.joinpath("groups"))))
