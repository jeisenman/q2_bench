from pathlib import Path

import yaml

PROTOCOL_CASE_COUNT = 11


def test_anti_leak_v1_records_detected_and_missed_findings() -> None:
    root = (
        Path(__file__).parents[5]
        / "src/workspaces/data_engineering/benchmarks/anti_leak/dates/09-26-26"
    )
    cases = yaml.safe_load((root / "cases.yaml").read_text(encoding="utf-8"))
    case = cases["cases"][0]

    assert case["agent_version"] == "1"
    assert (root / "assets/container_snapshot.json").is_file()
    assert (root / "hidden/expected_findings.yaml").is_file()
    assert cases["cases"][1]["id"] == "benchmark-change-anti-leak-protocol"
    assert cases["cases"][2]["id"] == "benchmark-change-scenario-001"
    assert len(cases["cases"]) == PROTOCOL_CASE_COUNT
    public_text = (root / "cases.yaml").read_text(encoding="utf-8")
    assert "baseline_expected_detected" not in public_text
    assert "baseline_expected_missed" not in public_text
    fixtures_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (root / "capabilities").glob("*.yaml")
    )
    assert "expected_finding:" not in fixtures_text
    assert "expected_findings:" not in fixtures_text


def test_resource_discovery_oracle_exposure_has_a_protected_regression() -> None:
    root = (
        Path(__file__).parents[5]
        / "src/workspaces/data_engineering/benchmarks/anti_leak/dates/09-26-26"
    )
    cases = yaml.safe_load((root / "cases.yaml").read_text(encoding="utf-8"))
    protected = yaml.safe_load(
        (root / "hidden/protocol_expected.yaml").read_text(encoding="utf-8")
    )

    assert any(case["id"] == "benchmark-change-scenario-009" for case in cases["cases"])
    regression = protected["cases"]["benchmark-change-scenario-009"]
    assert regression["expected_finding"] == (
        "public-metadata-discloses-oracle-outcome"
    )
    assert regression["regression"] == {
        "require_opaque_case_ids": True,
        "prohibit_public_outcome_labels": True,
    }


def test_prod_support_fallback_does_not_name_protected_expectation_path() -> None:
    root = (
        Path(__file__).parents[5]
        / "src/workspaces/data_engineering/benchmarks"
        / "production_support/dates/09-26-26"
    )
    public_text = "\n".join(
        (
            (root / "cases.yaml").read_text(encoding="utf-8"),
            (root / "README.md").read_text(encoding="utf-8"),
            (root / "capabilities/prior_run_log_fallback.yaml").read_text(
                encoding="utf-8"
            ),
        )
    )

    assert "hidden/prior_run_log_fallback.yaml" not in public_text
    assert "expected_classification:" not in public_text


def test_benchmark_image_does_not_copy_hidden_answers() -> None:
    dockerfile = (
        Path(__file__).parents[5] / "containers/anti-leak-benchmark/Dockerfile"
    ).read_text(encoding="utf-8")

    assert "dates/09-26-26/assets" in dockerfile
    assert "hidden" not in dockerfile
    assert "USER benchmark" in dockerfile


def test_suite_declares_protocol_subcapabilities() -> None:
    root = (
        Path(__file__).parents[5]
        / "src/workspaces/data_engineering/benchmarks/anti_leak/dates/09-26-26"
    )
    suite = yaml.safe_load((root / "suite.yaml").read_text(encoding="utf-8"))
    capabilities = suite["layers"]["capabilities"]

    assert capabilities["subcapabilities"]["controller_orchestration"] == [
        "sol_controller",
        "luna_public_hidden_worker",
        "luna_container_security_worker",
        "parallel_side_process",
    ]
    assert "benchmark-change-anti-leak-protocol" in (suite["layers"]["system"]["cases"])
    for fixture in capabilities["fixtures"]:
        configured = yaml.safe_load((root / fixture).read_text(encoding="utf-8"))
        assert configured["subcapabilities"]
        assert configured["cases"]


def test_prod_support_public_metadata_contains_no_expected_answers() -> None:
    root = (
        Path(__file__).parents[5]
        / "src/workspaces/data_engineering/benchmarks/production_support/dates"
    )
    for date_root in (
        root / "09-25-26",
        root / "09-26-26",
        root / "09-26-26-v2",
    ):
        public_paths = (
            date_root / "cases.yaml",
            *sorted((date_root / "capabilities").glob("*.yaml")),
        )
        for path in public_paths:
            text = path.read_text(encoding="utf-8")
            assert "expected_" not in text
            assert "expected_classification" not in text
            assert "required_client_findings" not in text
            assert "required_us_findings" not in text
            assert "required_ca_findings" not in text
            assert "required_overall_status" not in text
            assert "timeout_requirement" not in text


def test_candidate_inputs_exclude_hidden_and_prior_report_outputs() -> None:
    root = (
        Path(__file__).parents[5]
        / "src/workspaces/data_engineering/benchmarks/production_support/dates"
    )
    prohibited_names = {
        "mcp_debug_result.json",
        "mcp_debug_trace.json",
        "compact_evidence.jsonl",
        "holistic_evidence.json",
    }

    for date_root in (
        root / "09-25-26",
        root / "09-26-26",
        root / "09-26-26-v2",
    ):
        cases = yaml.safe_load((date_root / "cases.yaml").read_text(encoding="utf-8"))
        for case in cases["cases"]:
            inputs = tuple(Path(item) for item in case.get("candidate_inputs", ()))
            assert all("hidden" not in path.parts for path in inputs)
            assert prohibited_names.isdisjoint(path.name for path in inputs)


def test_candidate_health_evidence_contains_observations_not_outcomes() -> None:
    root = (
        Path(__file__).parents[5]
        / "src/workspaces/data_engineering/benchmarks/production_support/dates"
    )
    paths = (
        root / "09-25-26/evidence/current-us-cluster-observations.json",
        root / "09-25-26/evidence/current-ca-dag-processor.json",
        root / "09-25-26/evidence/current-ca-dag-processor-recovery.json",
        root / "09-25-26/evidence/current-ca-deployment-events.json",
        root / "09-26-26/assets/cluster_health_snapshot.json",
        root / "09-26-26-v2/assets/cluster_health_snapshot.json",
    )

    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert '"verdict"' not in text
        assert '"expected_interpretation"' not in text


def test_agentbench_image_excludes_hidden_benchmark_files() -> None:
    root = Path(__file__).parents[5]
    dockerignore = (root / ".dockerignore").read_text(encoding="utf-8")

    assert "src/workspaces/data_engineering/benchmarks/**/hidden" in dockerignore
