import json
from pathlib import Path

import pytest
import yaml

from workspaces.data_engineering.benchmarks import (
    BenchmarkCatalog,
    BenchmarkManifestError,
    default_catalog,
)

LARGE_RESEND_THRESHOLD = 100


def test_default_catalog_contains_visible_prod_support_benchmark() -> None:
    catalog = default_catalog()
    benchmark = catalog.get("data_engineering.production_operations.prod_support")

    assert benchmark.display_name == "prod-support"
    assert benchmark.group == "production_operations"
    assert benchmark.mlflow.experiment_name == "production_operations"
    assert benchmark.mlflow.run_tags["benchmark.id"] == benchmark.benchmark_id
    assert [item.display_name for item in catalog.list()] == [
        "anti-leak",
        "prod-support",
        "resource-discovery",
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


def test_prod_support_suite_registers_capability_fixtures() -> None:
    suite_root = (
        Path(__file__).parents[5]
        / "src/workspaces/data_engineering/benchmarks"
        / "production_support/dates/09-25-26"
    )
    suite = yaml.safe_load((suite_root / "suite.yaml").read_text(encoding="utf-8"))
    fixtures = suite["layers"]["capabilities"]["fixtures"]

    assert fixtures == [
        "capabilities/date_resolution.yaml",
        "capabilities/failure_discovery.yaml",
        "capabilities/log_classification.yaml",
        "capabilities/spark_evidence.yaml",
        "capabilities/cluster_health.yaml",
        "capabilities/channel_filtering.yaml",
        "capabilities/resend_routing.yaml",
        "capabilities/developer_message.yaml",
        "capabilities/prod_support_message.yaml",
    ]
    for relative_path in fixtures:
        fixture = yaml.safe_load(
            (suite_root / relative_path).read_text(encoding="utf-8")
        )
        assert fixture["schema_version"] == 1
        assert fixture["cases"]


def test_previous_snapshot_uses_bounded_links_and_v2_capabilities() -> None:
    root = (
        Path(__file__).parents[5]
        / "src/workspaces/data_engineering/benchmarks"
        / "production_support/dates/09-25-26"
    )
    cases = yaml.safe_load((root / "cases.yaml").read_text(encoding="utf-8"))
    case = cases["cases"][0]
    suite = yaml.safe_load((root / "suite.yaml").read_text(encoding="utf-8"))

    assert suite["operational_date"] == "2026-09-24"
    assert case["expected_ui_window"] == {
        "end_date_gte": "2026-09-24T09:00:00Z",
        "end_date_lt": "2026-09-25T09:00:00Z",
    }
    for link in case["expected_cluster_links"].values():
        assert "_flt_1_end_date=2026-09-25" in link
        assert "_flt_2_end_date=2026-09-24" in link
    assert (
        "capabilities/spark_evidence.yaml"
        in (suite["layers"]["capabilities"]["fixtures"])
    )
    assert case["omitted_from_data_internal"] == [
        "check_for_subscriber_client_errors",
        "log_cleanup",
        "opportunity_avro_aggregation_backfill",
        "opp_history_backfill",
    ]


def test_new_prod_support_snapshot_versions_september_25_data() -> None:
    suite_root = (
        Path(__file__).parents[5]
        / "src/workspaces/data_engineering/benchmarks"
        / "production_support/dates/09-26-26"
    )
    suite = yaml.safe_load((suite_root / "suite.yaml").read_text(encoding="utf-8"))
    cases = yaml.safe_load((suite_root / "cases.yaml").read_text(encoding="utf-8"))
    case = cases["cases"][0]
    previous_root = suite_root.with_name("09-25-26")
    previous_cases = yaml.safe_load(
        (previous_root / "cases.yaml").read_text(encoding="utf-8")
    )
    previous_case = previous_cases["cases"][0]

    assert suite["suite_date"] == "2026-09-26"
    assert suite["operational_date"] == "2026-09-25"
    assert suite["layers"]["system"]["cases"] == [
        "prod-support-us-ca-operational-2026-09-25"
    ]
    assert set(previous_case).issubset(case)
    assert case["expected_failure_counts"] == {}
    assert case["expected_cluster_links"] == {}
    assert case["expected_developer_message"] is None
    assert case["expected_prod_support_message"] is None

    fixtures = suite["layers"]["capabilities"]["fixtures"]
    assert "capabilities/spark_evidence.yaml" in fixtures
    assert "capabilities/prior_run_log_fallback.yaml" in fixtures
    assert "capabilities/cluster_health.yaml" in fixtures
    assert "capabilities/channel_filtering.yaml" in fixtures
    assert "capabilities/resend_routing.yaml" in fixtures


def test_new_snapshot_requires_parallel_timeout_and_resend_routing() -> None:
    root = (
        Path(__file__).parents[5]
        / "src/workspaces/data_engineering/benchmarks"
        / "production_support/dates/09-26-26/capabilities"
    )
    spark = yaml.safe_load((root / "spark_evidence.yaml").read_text(encoding="utf-8"))
    cluster = yaml.safe_load((root / "cluster_health.yaml").read_text(encoding="utf-8"))
    resend = yaml.safe_load((root / "resend_routing.yaml").read_text(encoding="utf-8"))

    spark_case = spark["cases"][0]
    assert set(spark_case["execution"]["start_in_parallel"]) == {
        "exact_airflow_task_log",
        "exact_oms_job_query",
    }
    assert spark_case["execution"]["mock_oms"]["actual_sleep_seconds"] == 0
    assert spark_case["execution"]["required_trace_events"] == [
        "oms_query_started",
        "airflow_log_started",
        "airflow_timeout_detected",
        "oms_query_cancelled",
    ]
    assert "expected_classification" not in spark_case
    assert cluster["cases"][0]["required_checks"] == [
        {
            "command": "kubectl get scaledobjects -n scheduler",
            "proves": "KEDA ScaledObject readiness and scaling state",
        },
        {
            "command": "kubectl get pods -n scheduler",
            "proves": "pod readiness, phase, and restart counts",
        },
    ]
    assert resend["cases"][0]["require_resource_discovery_skill"] is True
    assert resend["cases"][0]["large_resend_threshold"] == LARGE_RESEND_THRESHOLD
    assert (
        resend["cases"][0][
            "require_explicit_unresolved_status_without_reviewed_mapping"
        ]
        is True
    )


def test_new_snapshot_judge_punishes_missing_health_and_unresolved_routing() -> None:
    root = (
        Path(__file__).parents[5]
        / "src/workspaces/data_engineering/benchmarks"
        / "production_support/dates/09-26-26"
    )
    evaluation = yaml.safe_load((root / "evaluation.yaml").read_text(encoding="utf-8"))
    rubric = {item["id"]: item for item in evaluation["rubric"]}

    assert "either cluster-health bullet" in rubric["cluster_health"]["punish"]
    assert "DAG processor restart count" in rubric["cluster_health"]["punish"]
    assert (
        "routing remains unresolved" in (rubric["resource_discovery_routing"]["punish"])
    )


def test_new_snapshot_models_prior_run_log_fallback_without_fake_provenance() -> None:
    root = (
        Path(__file__).parents[5]
        / "src/workspaces/data_engineering/benchmarks"
        / "production_support/dates/09-26-26"
    )
    fixture = yaml.safe_load(
        (root / "capabilities/prior_run_log_fallback.yaml").read_text(encoding="utf-8")
    )
    evidence = json.loads(
        (root / "assets/multi_run_log_fallback.json").read_text(encoding="utf-8")
    )

    assert fixture["subcapabilities"] == [
        "same_task_identity",
        "reverse_chronological_run_search",
        "unavailable_log_handling",
        "terminal_evidence_selection",
    ]
    assert evidence["provenance"] == "synthetic"
    assert evidence["runs"][0]["log_status"] == "unavailable"
    assert "AirflowTaskTimeout" in evidence["runs"][1]["log"]


def test_new_snapshot_carries_prior_relationship_signals_evidence() -> None:
    root = (
        Path(__file__).parents[5]
        / "src/workspaces/data_engineering/benchmarks"
        / "production_support/dates/09-26-26"
    )
    cases = yaml.safe_load((root / "cases.yaml").read_text(encoding="utf-8"))
    asset_path = root / "assets/relationship_signals_prior_day.json"
    evidence = json.loads(asset_path.read_text(encoding="utf-8"))

    assert (
        str(asset_path.relative_to(Path(__file__).parents[5]))
        in (cases["cases"][0]["candidate_inputs"])
    )
    assert evidence["evidence_type"] == "prior_day_carry_forward"
    assert evidence["source_case_id"] == "prod-support-us-ca-2026-09-25"
    assert evidence["current_operational_date"] == "2026-09-25"
    assert evidence["oms_evidence"]["corroborating_memory_signal"] is False
    assert "classification" not in evidence
