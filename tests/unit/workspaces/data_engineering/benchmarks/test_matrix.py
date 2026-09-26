from pathlib import Path

import pytest

from adapters.inbound import MatrixInboundAdapter
from workspaces.data_engineering.benchmarks import (
    MatrixManifestError,
    build_candidate_prompt,
    build_matrix_judge_prompt,
    load_matrix_manifest,
)

MATRIX_PATH = (
    Path(__file__).parents[5]
    / "src/workspaces/data_engineering/benchmarks/production_support"
    / "dates/09-25-26/matrix.yaml"
)
PARALLEL_CONTAINERS = 6


def test_loads_prod_support_matrix_profiles_and_judge() -> None:
    manifest = load_matrix_manifest(MATRIX_PATH)

    assert manifest.judge.profile == "sol-xhigh"
    assert manifest.judge.reasoning_effort == "xhigh"
    assert [item.profile for item in manifest.candidates] == [
        "sol-controller-luna-xhigh-workers",
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
    assert manifest.runtime == "container"
    assert manifest.container_image == "agentsdk-agentbench:local"
    assert manifest.parallelism == PARALLEL_CONTAINERS


def test_matrix_prompts_include_rubric_and_local_evidence() -> None:
    manifest = load_matrix_manifest(MATRIX_PATH)
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
    assert "automation" in judge
    assert "capability_scores" in judge
    assert "Earlier comparable trace" in judge


def test_matrix_plan_groups_profiles_under_one_matrix() -> None:
    manifest = load_matrix_manifest(MATRIX_PATH)
    plan = MatrixInboundAdapter(Path.cwd()).plan(manifest)

    assert len(plan) == len(manifest.candidates)
    assert {item["matrix_id"] for item in plan} == {manifest.matrix_id}
    assert {item["judge_profile"] for item in plan} == {"sol-xhigh"}
    assert plan[0]["role"] == "controller"
    assert plan[0]["workers"] == ("luna-xhigh",)


def test_rejects_empty_matrix(tmp_path: Path) -> None:
    path = tmp_path / "matrix.yaml"
    path.write_text("schema_version: 1\n", encoding="utf-8")

    with pytest.raises(MatrixManifestError):
        load_matrix_manifest(path)


def test_rejects_invalid_worker_parallelism(tmp_path: Path) -> None:
    source = MATRIX_PATH.read_text(encoding="utf-8")
    path = tmp_path / "matrix.yaml"
    path.write_text(
        source.replace("        max_parallel: 6", "        max_parallel: 0"),
        encoding="utf-8",
    )

    with pytest.raises(MatrixManifestError, match="max_parallel"):
        load_matrix_manifest(path)


def test_defaults_parallelism_to_candidate_count(tmp_path: Path) -> None:
    source = MATRIX_PATH.read_text(encoding="utf-8")
    path = tmp_path / "matrix.yaml"
    path.write_text(source.replace("  parallelism: 6\n", ""), encoding="utf-8")

    manifest = load_matrix_manifest(path)

    assert manifest.parallelism == len(manifest.candidates)
