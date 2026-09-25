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


@dataclass(frozen=True, slots=True)
class Benchmark:
    """A validated benchmark definition."""

    benchmark_id: str
    display_name: str
    version: str
    group: str
    description: str
    mlflow: MlflowMapping

    @classmethod
    def from_manifest(cls, manifest: dict[str, Any]) -> Benchmark:
        """Create a benchmark from validated manifest data."""
        group = str(manifest["group"])
        benchmark_id = str(manifest["benchmark_id"])
        version = str(manifest["version"])
        return cls(
            benchmark_id=benchmark_id,
            display_name=str(manifest["display_name"]),
            version=version,
            group=group,
            description=str(manifest["description"]),
            mlflow=MlflowMapping(
                experiment_name=f"agentsdk/data_engineering/{group}",
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
                    }
                ),
            ),
        )
