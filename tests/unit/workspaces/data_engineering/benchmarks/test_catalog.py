from pathlib import Path

import pytest
import yaml

from workspaces.data_engineering.benchmarks import (
    BenchmarkCatalog,
    BenchmarkManifestError,
    default_catalog,
)

ROOT = Path(__file__).parents[5]
PROD_SUPPORT_ID = "data_engineering.production_operations.production_support"
MANIFEST = (
    ROOT
    / "src/workspaces/data_engineering/benchmarks/deprecated"
    / "production_support/manifest.yaml"
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


def test_deprecated_benchmarks_are_excluded_from_the_visible_list() -> None:
    catalog = default_catalog()
    visible = {item.benchmark_id for item in catalog.list()}
    retired = {item.benchmark_id for item in catalog.list_deprecated()}

    assert PROD_SUPPORT_ID in retired
    assert PROD_SUPPORT_ID not in visible
    assert PROD_SUPPORT_ID in {
        item.benchmark_id for item in catalog.list(include_deprecated=True)
    }


def test_deprecated_benchmark_records_why_it_is_retained() -> None:
    retired = default_catalog().get(PROD_SUPPORT_ID)

    assert retired.is_active is False
    assert retired.deprecation is not None
    assert retired.deprecation.since == "2026-09-29"
    assert retired.deprecation.reason
    assert retired.deprecation.retained_for
    assert retired.mlflow.run_tags["benchmark.status"] == "deprecated"


def test_deprecated_status_requires_a_documented_reason(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "benchmark_id": "data_engineering.group.thing",
                "display_name": "thing",
                "version": "1.0.0",
                "group": "group",
                "description": "A thing.",
                "status": "deprecated",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(BenchmarkManifestError, match="requires a deprecated mapping"):
        BenchmarkCatalog.load(tmp_path)


def test_unknown_status_is_rejected(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "benchmark_id": "data_engineering.group.thing",
                "display_name": "thing",
                "version": "1.0.0",
                "group": "group",
                "description": "A thing.",
                "status": "retired",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(BenchmarkManifestError, match="status must be one of"):
        BenchmarkCatalog.load(tmp_path)
