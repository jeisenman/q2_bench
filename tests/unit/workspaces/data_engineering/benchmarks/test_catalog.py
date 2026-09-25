import json
from pathlib import Path

import pytest
import yaml

from workspaces.data_engineering.benchmarks import (
    BenchmarkCatalog,
    BenchmarkManifestError,
    default_catalog,
)


def test_default_catalog_contains_visible_prod_support_benchmark() -> None:
    benchmark = default_catalog().list()[0]

    assert benchmark.display_name == "prod-support"
    assert benchmark.group == "production_operations"
    assert benchmark.mlflow.experiment_name == "production_operations"
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


def test_prod_support_case_combines_us_and_ca_expectations() -> None:
    captured_ca_dag_count = 35
    expected_us_failure_count = 7
    cases_path = (
        Path(__file__).parents[5]
        / "src/workspaces/data_engineering/benchmarks"
        / "production_support/dates/09-25-26/cases.yaml"
    )
    configured = yaml.safe_load(cases_path.read_text(encoding="utf-8"))["cases"]
    case = next(
        item for item in configured if item["id"] == "prod-support-us-ca-2026-09-25"
    )

    assert case["prompt"] == "Do prod support"
    assert case["expected_regions"] == ["US-01", "CA-02"]
    assert case["expected_failure_counts"] == {
        "US-01": expected_us_failure_count,
        "CA-02": 0,
    }
    assert len(case["expected_failure_ids"]) == expected_us_failure_count
    assert case["require_reported_dags_exist"] is True
    assert len(case["expected_dag_ids"]) > captured_ca_dag_count
    assert case["expected_l3_main_graph_counts"] == {"US-01": 78, "CA-02": 6}
    assert case["expected_infrastructure_statuses"] == {
        "US-01": "healthy",
        "CA-02": "dag_processor_unhealthy",
    }
    assert case["expected_remediation_policy"] == {
        "mode": "suggestion_only",
        "automatic_bounce": False,
        "automatic_actions": [],
        "suggest_bounce_on_missing_dags_logs_and_restarts": True,
    }

    evidence_by_region = {
        region: json.loads(
            (cases_path.parent / relative_path).read_text(encoding="utf-8")
        )
        for region, relative_path in case["infrastructure_evidence_uris"].items()
    }
    assert evidence_by_region["US-01"]["verdict"] == "healthy"
    ca_evidence = evidence_by_region["CA-02"]["evidence"]
    assert ca_evidence["airflow_health"]["dag_processor"]["status"] == "unhealthy"
    assert ca_evidence["oms"]["corroborates_claim"] is False
    assert ca_evidence["airflow_dag_inventory"]["l3_main_graph_counts"] == {
        "US-01": 78,
        "CA-02": 6,
    }
    removed_ids = {
        "current-ca-dags-exist-2026-09-25",
        "today-2026-09-25",
        "default-2026-09-25",
    }
    assert removed_ids.isdisjoint(item["id"] for item in configured)


def test_prod_support_suite_defines_three_evaluation_layers() -> None:
    suite_path = (
        Path(__file__).parents[5]
        / "src/workspaces/data_engineering/benchmarks"
        / "production_support/dates/09-25-26/suite.yaml"
    )
    suite = yaml.safe_load(suite_path.read_text(encoding="utf-8"))

    assert suite["suite_date"] == "2026-09-25"
    assert set(suite["layers"]) == {"capabilities", "coordination", "system"}
    assert "diagnosis_accuracy" in suite["layers"]["capabilities"]["dimensions"]
    assert "evidence_handoff" in suite["layers"]["coordination"]["dimensions"]
    assert "prod-support-us-ca-2026-09-25" in suite["layers"]["system"]["cases"]
