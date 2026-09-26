from pathlib import Path

import pytest

from adapters.inbound import MatrixInboundAdapter
from workspaces.data_engineering.benchmarks import (
    MatrixManifestError,
    build_candidate_prompt,
    build_matrix_judge_prompt,
    load_matrix_run,
)

ROOT = Path(__file__).parents[5]
AGENTS_PATH = ROOT / "src/workspaces/data_engineering/benchmarks/agent-manifest.yaml"
BENCHMARK_PATH = (
    ROOT
    / "src/workspaces/data_engineering/benchmarks/production_support"
    / "dates/09-25-26/evaluation.yaml"
)
CASES_PATH = BENCHMARK_PATH.with_name("cases.yaml")
CASE_ID = "prod-support-us-ca-2026-09-25"
PARALLEL_CONTAINERS = 6


def load_run(
    configuration_ids: tuple[str, ...] = (),
):
    return load_matrix_run(
        BENCHMARK_PATH,
        AGENTS_PATH,
        CASES_PATH,
        CASE_ID,
        configuration_ids,
    )


def test_loads_prod_support_matrix_profiles_and_judge() -> None:
    manifest = load_run()

    assert manifest.judge.profile == "sol-xhigh-judge"
    assert manifest.judge.reasoning_effort == "xhigh"
    assert [item.profile for item in manifest.candidates] == [
        "sol-controller-luna-xhigh-workers",
        "sol-light-luna-high-workers",
        "sol-medium-luna-high-workers",
        "sol-light",
        "terra-medium",
        "luna-xhigh",
        "luna-high",
        "luna-medium",
        "luna-low",
    ]
    orchestration = manifest.candidates[0]
    assert orchestration.role == "controller"
    assert orchestration.capabilities == (
        "task_decomposition",
        "parallel_coordination",
        "evidence_synthesis",
        "final_reporting",
    )
    assert orchestration.workers[0].profile == "luna-xhigh"
    assert orchestration.workers[0].max_parallel == PARALLEL_CONTAINERS
    selected = load_run(("sol-light-luna-high-workers",))
    assert selected.candidates[0].workers[0].profile == "luna-high"
    assert manifest.runtime == "container"
    assert manifest.container_image == "agentsdk-agentbench:local"
    assert manifest.parallelism == PARALLEL_CONTAINERS


def test_matrix_prompts_include_rubric_and_local_evidence() -> None:
    manifest = load_run()
    candidate = build_candidate_prompt(manifest)
    judge = build_matrix_judge_prompt(
        manifest,
        {"tool_calls": ["airflow"]},
        baseline={"elapsed_seconds": 10},
    )

    assert str(manifest.dataset) in candidate
    assert "read-only" in candidate
    assert "luna-xhigh" in candidate
    assert "airflow_log_analysis" in candidate
    assert "page backward through prior runs of the same DAG and task" in candidate
    assert "start exact Airflow-log and OMS queries concurrently" in candidate
    assert "US Cluster Health and CA Cluster Health" in candidate
    assert "resend exceeds 100 unique events" in candidate
    assert "Do not claim a check was performed without trace evidence" in candidate
    assert "automation" in judge
    assert "capability_scores" in judge
    assert "Earlier comparable trace" in judge


def test_matrix_plan_groups_profiles_under_one_matrix() -> None:
    manifest = load_run()
    plan = MatrixInboundAdapter(Path.cwd()).plan(manifest)

    assert len(plan) == len(manifest.candidates)
    assert {item["matrix_id"] for item in plan} == {manifest.matrix_id}
    assert {item["judge_profile"] for item in plan} == {"sol-xhigh-judge"}
    assert plan[0]["role"] == "controller"
    assert plan[0]["workers"] == ("luna-xhigh",)


def test_rejects_empty_matrix(tmp_path: Path) -> None:
    path = tmp_path / "evaluation.yaml"
    path.write_text("schema_version: 1\n", encoding="utf-8")

    with pytest.raises(MatrixManifestError):
        load_matrix_run(path, AGENTS_PATH, CASES_PATH, CASE_ID)


def test_rejects_invalid_worker_parallelism(tmp_path: Path) -> None:
    source = AGENTS_PATH.read_text(encoding="utf-8")
    path = tmp_path / "agents.yaml"
    path.write_text(
        source.replace("        max_parallel: 6", "        max_parallel: 0"),
        encoding="utf-8",
    )

    with pytest.raises(MatrixManifestError, match="max_parallel"):
        load_matrix_run(BENCHMARK_PATH, path, CASES_PATH, CASE_ID)


def test_defaults_parallelism_to_candidate_count(tmp_path: Path) -> None:
    source = BENCHMARK_PATH.read_text(encoding="utf-8")
    path = tmp_path / "evaluation.yaml"
    path.write_text(source.replace("  parallelism: 6\n", ""), encoding="utf-8")

    manifest = load_matrix_run(path, AGENTS_PATH, CASES_PATH, CASE_ID)

    assert manifest.parallelism == len(manifest.candidates)


def test_rejects_unknown_configuration() -> None:
    with pytest.raises(MatrixManifestError, match="unknown agent configuration"):
        load_run(("missing",))
