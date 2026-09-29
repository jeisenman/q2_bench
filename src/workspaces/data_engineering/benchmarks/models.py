"""Immutable benchmark catalog models."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True, slots=True)
class MlflowMapping:
    """MLflow experiment and tag mapping for a benchmark."""

    experiment_name: str
    experiment_tags: MappingProxyType[str, object]
    run_tags: MappingProxyType[str, str]


ACTIVE = "active"
DEPRECATED = "deprecated"
BENCHMARK_STATUSES = frozenset({ACTIVE, DEPRECATED})


@dataclass(frozen=True, slots=True)
class Deprecation:
    """Why a benchmark was retired and what its data remains useful for."""

    since: str
    reason: str
    retained_for: str


@dataclass(frozen=True, slots=True)
class Benchmark:
    """A validated benchmark definition."""

    benchmark_id: str
    display_name: str
    version: str
    group: str
    description: str
    mlflow: MlflowMapping
    status: str = ACTIVE
    deprecation: Deprecation | None = None

    @property
    def is_active(self) -> bool:
        """Return whether this benchmark still scores current behavior."""
        return self.status == ACTIVE

    @classmethod
    def from_manifest(cls, manifest: dict[str, Any]) -> Benchmark:
        """Create a benchmark from validated manifest data."""
        group = str(manifest["group"])
        benchmark_id = str(manifest["benchmark_id"])
        version = str(manifest["version"])
        status = str(manifest.get("status", ACTIVE))
        raw_deprecation = manifest.get("deprecated")
        deprecation = (
            Deprecation(
                since=str(raw_deprecation["since"]),
                reason=str(raw_deprecation["reason"]).strip(),
                retained_for=str(raw_deprecation["retained_for"]).strip(),
            )
            if isinstance(raw_deprecation, dict)
            else None
        )
        return cls(
            benchmark_id=benchmark_id,
            display_name=str(manifest["display_name"]),
            version=version,
            group=group,
            description=str(manifest["description"]),
            status=status,
            deprecation=deprecation,
            mlflow=MlflowMapping(
                experiment_name=group,
                experiment_tags=MappingProxyType(
                    {
                        "workspace": "data_engineering",
                        "benchmark.group": group,
                    }
                ),
                run_tags=MappingProxyType(
                    {
                        "workspace": "data_engineering",
                        "benchmark.group_path": f"data_engineering/{group}",
                        "benchmark.id": benchmark_id,
                        "benchmark.version": version,
                        "benchmark.status": status,
                    }
                ),
            ),
        )
