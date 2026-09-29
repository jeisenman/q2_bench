from pathlib import Path

import pytest
import yaml

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
    / "src/workspaces/data_engineering/benchmarks/deprecated/production_support"
    / "dates/09-27-26/evaluation.yaml"
)
CASES_PATH = BENCHMARK_PATH.with_name("cases.yaml")
CASE_ID = "handoff-bench-builder-agent-2026-09-26"
PARALLEL_CONTAINERS = 5
MAX_SUBAGENT_PARALLELISM = 5
BENCH_BUILDER_CASE_PARALLELISM = 2


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

    assert manifest.judge.profile == "sol-high-judge"
    assert manifest.judge.reasoning_effort == "high"
    assert [item.profile for item in manifest.candidates] == [
        "sol-controller-luna-xhigh-workers",
        "sol-light-luna-high-workers",
        "sol-medium-luna-high-workers",
        "sol-light",
        "luna-high-controller-luna-high-workers",
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
    assert orchestration.workers[0].max_parallel == MAX_SUBAGENT_PARALLELISM
    selected = load_run(("sol-light-luna-high-workers",))
    assert selected.candidates[0].workers[0].profile == "luna-high"
    assert manifest.runtime == "container"
    assert manifest.container_image == "agentsdk-agentbench:local"
    assert manifest.parallelism == PARALLEL_CONTAINERS


def test_matrix_prompts_include_handoff_contract_and_local_evidence() -> None:
    manifest = load_run()
    candidate = build_candidate_prompt(manifest)
    judge = build_matrix_judge_prompt(
        manifest,
        {"tool_calls": ["airflow"]},
        baseline={"elapsed_seconds": 10},
    )

    assert str(manifest.dataset) in candidate
    assert "luna-xhigh" in candidate
    assert "airflow_failure_discovery" in candidate
    assert "Configured workers are leaf agents" in candidate
    assert "must not spawn, hand off to, or delegate" in candidate
    assert candidate.startswith(
        "Run the named-agent production-support handoff benchmark."
    )
    assert "Use no more than 2 concurrent handoffs." in candidate
    assert "Orchestrator -> ClusterAgent" in candidate
    assert "Orchestrator -> TriageManager" in candidate
    assert "Orchestrator -> Reporter" in candidate
    assert "Orchestrator -> BenchBuilderAgent" in candidate
    assert "Reporter is the authoritative final-output handoff." in candidate
    assert "Build only a new review-required case" in candidate
    assert "Retain all normal MCP report fields" in candidate
    assert "Do not mutate production." in candidate
    assert "Never expose raw logs or hidden expectations" in candidate
    assert "capability_scores" in judge
    assert "Earlier comparable trace" in judge
    assert "named_agent_invocation" in judge
    assert "handoff_input_contract" in judge
    assert "handoff_output_contract" in judge
    assert "output_authority" in judge
    assert "mcp_output_continuity" in judge
    assert "Case applicability" in judge
    assert "marked false are excluded" in judge
    assert "handoff_ordering is false" in judge


def test_matrix_plan_groups_profiles_under_one_matrix() -> None:
    manifest = load_run()
    plan = MatrixInboundAdapter(Path.cwd()).plan(manifest)

    assert len(plan) == len(manifest.candidates)
    assert {item["matrix_id"] for item in plan} == {manifest.matrix_id}
    assert {item["judge_profile"] for item in plan} == {"sol-high-judge"}
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
        source.replace("        max_parallel: 5", "        max_parallel: 0"),
        encoding="utf-8",
    )

    with pytest.raises(MatrixManifestError, match="max_parallel"):
        load_matrix_run(BENCHMARK_PATH, path, CASES_PATH, CASE_ID)


def test_rejects_worker_parallelism_above_repository_limit(tmp_path: Path) -> None:
    source = AGENTS_PATH.read_text(encoding="utf-8")
    path = tmp_path / "agents.yaml"
    path.write_text(
        source.replace("        max_parallel: 5", "        max_parallel: 6"),
        encoding="utf-8",
    )

    with pytest.raises(
        MatrixManifestError,
        match="max_parallel must not exceed 5",
    ):
        load_matrix_run(BENCHMARK_PATH, path, CASES_PATH, CASE_ID)


def test_rejects_nested_worker_configuration(tmp_path: Path) -> None:
    source = AGENTS_PATH.read_text(encoding="utf-8")
    path = tmp_path / "agents.yaml"
    path.write_text(
        source.replace(
            "        max_parallel: 5",
            "        max_parallel: 5\n        workers: []",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(MatrixManifestError, match="must be leaf agents"):
        load_matrix_run(BENCHMARK_PATH, path, CASES_PATH, CASE_ID)


def test_rejects_worker_delegation_configuration(tmp_path: Path) -> None:
    source = AGENTS_PATH.read_text(encoding="utf-8")
    path = tmp_path / "agents.yaml"
    path.write_text(
        source.replace(
            "        max_parallel: 5",
            "        max_parallel: 5\n        can_delegate: true",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(MatrixManifestError, match="must be leaf agents"):
        load_matrix_run(BENCHMARK_PATH, path, CASES_PATH, CASE_ID)


def test_defaults_parallelism_to_candidate_count(tmp_path: Path) -> None:
    source = BENCHMARK_PATH.read_text(encoding="utf-8")
    path = tmp_path / "evaluation.yaml"
    path.write_text(source.replace("  parallelism: 5\n", ""), encoding="utf-8")

    manifest = load_matrix_run(path, AGENTS_PATH, CASES_PATH, CASE_ID)

    assert manifest.parallelism == len(manifest.candidates)


def test_rejects_unknown_configuration() -> None:
    with pytest.raises(MatrixManifestError, match="unknown agent configuration"):
        load_run(("missing",))


def test_loads_today_bench_builder_handoff_contract() -> None:
    manifest = load_matrix_run(
        BENCHMARK_PATH,
        AGENTS_PATH,
        CASES_PATH,
        "handoff-bench-builder-agent-2026-09-26",
        ("sol-light",),
    )

    assert manifest.handoff_contract is not None
    assert manifest.handoff_contract.max_parallel == BENCH_BUILDER_CASE_PARALLELISM
    assert manifest.handoff_contract.output_authority == "Reporter"
    assert [agent.name for agent in manifest.handoff_contract.agents] == [
        "ClusterAgent",
        "TriageManager",
        "Reporter",
        "BenchBuilderAgent",
    ]
    prompt = build_candidate_prompt(manifest)
    judge = build_matrix_judge_prompt(manifest, {"events": []})
    assert "Orchestrator -> BenchBuilderAgent" in prompt
    assert "starts_after=none" in prompt
    assert "Retain all normal MCP report fields" in prompt
    assert "handoff_scores" in judge
    assert "BenchBuilderAgent" in judge


def test_rejects_handoff_parallelism_above_repository_limit(
    tmp_path: Path,
) -> None:
    cases = CASES_PATH.read_text(encoding="utf-8")
    path = tmp_path / "cases.yaml"
    path.write_text(
        cases.replace("      max_parallel: 2", "      max_parallel: 6"),
        encoding="utf-8",
    )

    with pytest.raises(
        MatrixManifestError,
        match="handoff max_parallel must be between 1 and 5",
    ):
        load_matrix_run(
            BENCHMARK_PATH,
            AGENTS_PATH,
            path,
            "handoff-bench-builder-agent-2026-09-26",
            ("sol-light",),
        )


def test_full_system_case_declares_unordered_handoffs_and_complete_inputs() -> None:
    manifest = load_matrix_run(
        BENCHMARK_PATH,
        AGENTS_PATH,
        CASES_PATH,
        "prod-support-us-ca-operational-2026-09-26",
        ("sol-light-luna-high-workers",),
    )

    assert manifest.handoff_contract is not None
    assert [agent.name for agent in manifest.handoff_contract.agents] == [
        "ClusterAgent",
        "TriageManager",
        "Reporter",
    ]
    assert all(not agent.starts_after for agent in manifest.handoff_contract.agents)
    assert dict(manifest.applicability)["handoff_ordering"] is False
    assert any(path.name == "regional_handoff.py" for path in manifest.candidate_inputs)
    assert build_candidate_prompt(manifest).startswith(
        "Run the prod-support benchmark using only local recorded evidence."
    )


def test_rejects_incomplete_or_unknown_applicability(tmp_path: Path) -> None:
    document = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))
    selected = document["cases"][0]["evaluation_applicability"]
    selected.pop("token_efficiency")
    selected["unknown_metric"] = True
    path = tmp_path / "cases.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        MatrixManifestError,
        match="missing: token_efficiency; unknown: unknown_metric",
    ):
        load_matrix_run(
            BENCHMARK_PATH,
            AGENTS_PATH,
            path,
            "prod-support-us-ca-operational-2026-09-26",
            ("sol-light",),
        )
