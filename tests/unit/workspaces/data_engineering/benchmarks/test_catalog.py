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


def test_current_ca_case_requires_reported_dags_to_exist() -> None:
    captured_dag_count = 35
    cases_path = (
        Path(__file__).parents[5]
        / "src/workspaces/data_engineering/benchmarks/groups"
        / "production_operations/prod_support/cases.yaml"
    )
    configured = yaml.safe_load(cases_path.read_text(encoding="utf-8"))["cases"]
    case = next(
        item for item in configured if item["id"] == "current-ca-dags-exist-2026-09-25"
    )

    assert case["region"] == "CA-02"
    assert case["require_reported_dags_exist"] is True
    assert len(case["expected_dag_ids"]) == captured_dag_count
    assert case["expected_failure_ids"] == []
    assert case["expected_l3_main_graph_counts"] == {"US-01": 78, "CA-02": 6}
    evidence_path = cases_path.parent / case["infrastructure_evidence_uri"]
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["evidence"]["airflow_health"]["dag_processor"]["status"] == (
        "unhealthy"
    )
    assert evidence["evidence"]["oms"]["corroborates_claim"] is False
    assert evidence["evidence"]["airflow_dag_inventory"]["l3_main_graph_counts"] == {
        "US-01": 78,
        "CA-02": 6,
    }
    assert evidence["verdict"] == "confirmed_by_airflow_health_not_correlated_in_oms"


def test_today_case_includes_healthy_us_infrastructure_evidence() -> None:
    expected_active_dags = 209
    expected_active_l3_main_dags = 153
    cases_path = (
        Path(__file__).parents[5]
        / "src/workspaces/data_engineering/benchmarks/groups"
        / "production_operations/prod_support/cases.yaml"
    )
    configured = yaml.safe_load(cases_path.read_text(encoding="utf-8"))["cases"]
    case = next(item for item in configured if item["id"] == "today-2026-09-25")

    evidence_path = cases_path.parent / case["infrastructure_evidence_uri"]
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert case["expected_infrastructure_status"] == "healthy"
    assert case["expected_active_dag_count"] == expected_active_dags
    assert case["expected_active_l3_main_dag_count"] == expected_active_l3_main_dags
    assert evidence["evidence"]["airflow_health"]["dag_processor"]["status"] == (
        "healthy"
    )
    assert (
        evidence["evidence"]["airflow_dag_inventory"]["active_dag_count"]
        == expected_active_dags
    )
    assert evidence["verdict"] == "healthy"
