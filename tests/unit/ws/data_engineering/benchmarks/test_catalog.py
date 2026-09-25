from pathlib import Path

import pytest

from agentsdk.ws.data_engineering.benchmarks import (
    BenchmarkCatalog,
    BenchmarkManifestError,
    default_catalog,
)


def test_default_catalog_contains_visible_prod_support_benchmark() -> None:
    benchmark = default_catalog().list()[0]

    assert benchmark.display_name == "prod-support"
    assert benchmark.group == "production_operations"
    assert (
        benchmark.mlflow.experiment_name
        == "agentsdk/data_engineering/production_operations"
    )
    assert benchmark.mlflow.run_tags["benchmark.id"] == benchmark.benchmark_id


def test_catalog_rejects_invalid_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "group" / "benchmark" / "manifest.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("schema_version: 1\ngroup: Bad Group\n", encoding="utf-8")

    with pytest.raises(BenchmarkManifestError, match="missing required fields"):
        BenchmarkCatalog.load(tmp_path)


def test_catalog_reports_unknown_id() -> None:
    with pytest.raises(KeyError, match="Unknown benchmark ID"):
        default_catalog().get("missing.benchmark")
