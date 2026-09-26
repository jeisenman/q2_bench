import subprocess
from pathlib import Path

import yaml

from workspaces.data_engineering.benchmarks import (
    build_candidate_prompt,
    build_matrix_judge_prompt,
    default_catalog,
    load_matrix_run,
)

ROOT = Path(__file__).parents[5]
BENCHMARK_ROOT = (
    ROOT / "src/workspaces/data_engineering/benchmarks/prod_bench/dates/09-26-26"
)
AGENTS_PATH = ROOT / "src/workspaces/data_engineering/benchmarks/agent-manifest.yaml"
CASES_PATH = BENCHMARK_ROOT / "cases.yaml"
CAPABILITY_COUNT = 14
MAX_PARALLELISM = 5


def test_catalog_contains_prod_bench() -> None:
    benchmark = default_catalog().get(
        "data_engineering.production_operations.prod_bench"
    )

    assert benchmark.display_name == "prod-bench"
    assert benchmark.version == "1.1.0"


def test_prod_bench_registers_one_evaluation_per_capability() -> None:
    suite = yaml.safe_load((BENCHMARK_ROOT / "suite.yaml").read_text(encoding="utf-8"))
    evaluations = suite["layers"]["capabilities"]["evaluations"]
    cases = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))["cases"]
    cases_by_id = {case["id"]: case for case in cases}

    assert len(evaluations) == CAPABILITY_COUNT
    assert len(cases_by_id) == CAPABILITY_COUNT
    assert len({item["capability"] for item in evaluations}) == CAPABILITY_COUNT
    for item in evaluations:
        evaluation = yaml.safe_load(
            (BENCHMARK_ROOT / item["manifest"]).read_text(encoding="utf-8")
        )
        assert evaluation["capability"] == item["capability"]
        assert evaluation["rubric"][0]["id"] == item["capability"]
        assert evaluation["rubric"][0]["weight"] == 1.0
        assert len(evaluation["rubric"]) == 1
        assert evaluation["execution"]["parallelism"] <= MAX_PARALLELISM
        assert cases_by_id[item["case"]]["prompt"]
        manifest = load_matrix_run(
            BENCHMARK_ROOT / item["manifest"],
            AGENTS_PATH,
            CASES_PATH,
            item["case"],
            ("sol-light",),
        )
        assert manifest.capability == item["capability"]
        assert manifest.case_prompt == cases_by_id[item["case"]]["prompt"]


def test_capability_prompt_does_not_inject_full_report_contract() -> None:
    manifest = load_matrix_run(
        BENCHMARK_ROOT / "evaluations/prior_run_fallback.yaml",
        AGENTS_PATH,
        CASES_PATH,
        "prior-run-fallback",
        ("sol-light",),
    )

    prompt = build_candidate_prompt(manifest)
    judge = build_matrix_judge_prompt(manifest, {"events": []})

    assert manifest.capability == "prior_run_fallback"
    assert "Capability under test: prior_run_fallback" in prompt
    assert "select the first prior same-DAG" in prompt
    assert "Do not produce the complete prod-support report" in prompt
    assert "# Prod Support Report" not in prompt
    assert "Message for developer:" not in prompt
    assert "isolated prior_run_fallback capability" in judge


def test_capability_prompt_does_not_force_worker_delegation() -> None:
    manifest = load_matrix_run(
        BENCHMARK_ROOT / "evaluations/date_window.yaml",
        AGENTS_PATH,
        CASES_PATH,
        "date-window",
        ("sol-light-luna-high-workers",),
    )

    prompt = build_candidate_prompt(manifest)

    assert "luna-high" in prompt
    assert "use them only when they help the named capability" in prompt
    assert "Delegate independent work" not in prompt


def test_public_cases_do_not_embed_expected_answers() -> None:
    cases = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))["cases"]

    for case in cases:
        assert not any(key.startswith("expected") for key in case)


def test_reporting_cases_cover_grouping_region_purity_and_contradictions() -> None:
    cases = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))["cases"]
    by_id = {case["id"]: case for case in cases}

    data_internal = "\n".join(by_id["data-internal-message"]["instructions"])
    assert "Never place CA findings under US" in data_internal
    assert "Group clients that fail on the same job" in data_internal
    assert "credit_migration_matrix or CMM" in data_internal
    assert "Use no periods" in data_internal

    regional = "\n".join(by_id["regional-consistency"]["instructions"])
    assert "wrong region" in regional
    assert "contradicts the authoritative evidence" in regional

    grouped = "\n".join(by_id["grouped-reporting"]["instructions"])
    assert "Group all clients sharing one job" in grouped
    assert "Group all jobs for one client" in grouped


def test_spark_mock_returns_explicit_airflow_timeout() -> None:
    script = BENCHMARK_ROOT / "assets/mock_spark_sources.py"

    completed = subprocess.run(
        ["python", str(script), "airflow"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "AirflowTaskTimeout" in completed.stdout
