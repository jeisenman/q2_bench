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
