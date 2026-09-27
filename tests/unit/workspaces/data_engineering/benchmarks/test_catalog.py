from pathlib import Path

import pytest
import yaml

from workspaces.data_engineering.benchmarks import (
    BenchmarkCatalog,
    BenchmarkManifestError,
    default_catalog,
)

ROOT = Path(__file__).parents[5]
MANIFEST = (
    ROOT / "src/workspaces/data_engineering/benchmarks/production_support/manifest.yaml"
)


def test_default_catalog_contains_production_support_v1() -> None:
    catalog = default_catalog()
    benchmark = catalog.get("data_engineering.production_operations.production_support")

    assert benchmark.display_name == "production-support"
    assert benchmark.version == "1.0.0"
    assert benchmark.group == "production_operations"


def test_production_support_manifest_defines_only_current_run() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))

    assert manifest["runs"] == [
        {
            "id": "09-27-26",
            "suite": "dates/09-27-26/suite.yaml",
            "cases": "dates/09-27-26/cases.yaml",
            "evaluation": "dates/09-27-26/evaluation.yaml",
        }
    ]


def test_catalog_rejects_invalid_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "group" / "benchmark" / "manifest.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("schema_version: 1\ngroup: Bad Group\n", encoding="utf-8")

    with pytest.raises(BenchmarkManifestError, match="missing required fields"):
        BenchmarkCatalog.load(tmp_path)


def test_catalog_reports_unknown_id() -> None:
    with pytest.raises(KeyError, match="Unknown benchmark ID"):
        default_catalog().get("missing.benchmark")
