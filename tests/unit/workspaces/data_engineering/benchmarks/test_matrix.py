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
PARALLEL_CONTAINERS = 3


def test_loads_prod_support_matrix_profiles_and_judge() -> None:
    manifest = load_matrix_manifest(MATRIX_PATH)

    assert manifest.judge.profile == "sol-xhigh"
    assert manifest.judge.reasoning_effort == "xhigh"
    assert [item.profile for item in manifest.candidates] == [
        "sol-light",
        "terra-medium",
        "luna-xhigh",
        "luna-high",
        "luna-medium",
        "luna-low",
    ]
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
    assert "automation" in judge
    assert "Earlier comparable trace" in judge


def test_matrix_plan_groups_profiles_under_one_matrix() -> None:
    manifest = load_matrix_manifest(MATRIX_PATH)
    plan = MatrixInboundAdapter(Path.cwd()).plan(manifest)

    assert len(plan) == len(manifest.candidates)
    assert {item["matrix_id"] for item in plan} == {manifest.matrix_id}
    assert {item["judge_profile"] for item in plan} == {"sol-xhigh"}


def test_rejects_empty_matrix(tmp_path: Path) -> None:
    path = tmp_path / "matrix.yaml"
    path.write_text("schema_version: 1\n", encoding="utf-8")

    with pytest.raises(MatrixManifestError):
        load_matrix_manifest(path)
