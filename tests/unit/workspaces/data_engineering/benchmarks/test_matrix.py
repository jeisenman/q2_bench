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
PARALLEL_CONTAINERS = 5
MAX_SUBAGENT_PARALLELISM = 5


def _assert_reporting_prompt(candidate: str) -> None:
    assert "URLs to validate" in candidate
    assert "Message for developer:" in candidate
    assert ":bangbang: PROD SUPPORT 2026-09-24 :bangbang:" in candidate
    assert "one Reporting Agent pass" in candidate
    assert "Group clients that failed on the same job" in candidate
    assert "Mention every client-job pair exactly once" in candidate
    assert "represented omission codes on the final detail line" in candidate
    assert "Use no periods in Data Internal" in candidate
    assert "suggestion-only" in candidate
    assert "return it verbatim" in candidate
    assert "must not rewrite" in candidate
    assert (
        "Resend <number> opportunities for <client names> on "
        "[Resend Opportunity Snapshots](<approved link>) for date <MM-DD-YY>."
    ) in candidate
    assert (
        "Ask a human to resolve the client identity for "
        "<unresolved client labels> before proposing remediation "
        "for date <MM-DD-YY>."
    ) in candidate
    assert "retired DAG processor" in candidate


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
    assert "airflow_failure_discovery" in candidate
    assert "Configured workers are leaf agents" in candidate
    assert "must not spawn, hand off to, or delegate" in candidate
    assert "one Cluster Agent handoff and one Airflow Agent handoff concurrently" in (
        candidate
    )
    assert "regional calls are not additional agents" in candidate
    assert "active DAG count" in candidate
    assert "DAG-processor health" in candidate
    assert "never infer parsing health from the failed-task inventory" in candidate
    assert candidate.startswith(
        "Run the prod-support benchmark using only local recorded evidence."
    )
    assert "# Prod Support Report — 2026-09-24 operational day" in candidate
    assert (
        "Window: `2026-09-24 05:00:00 UTC` through `2026-09-25 05:00:00 UTC`"
    ) in candidate
    assert (
        "?_flt_1_end_date=2026-09-25T05:00:00Z"
        "&_flt_3_state=failed"
        "&_flt_2_end_date=2026-09-24T05:00:00Z#"
    ) in candidate
    assert "%3A" not in candidate
    assert "/dags/<dag-id>/grid?status=failed" in candidate
    assert "compact_brief" in candidate
    assert "compact_evidence.py" in candidate
    assert "--output /tmp/prod-support-compact-evidence.json" in candidate
    assert "Do not reopen inputs or outputs" in candidate
    assert "invoke jq" in candidate
    assert "raw logs" in candidate
    _assert_reporting_prompt(candidate)
    assert "automation" in judge
    assert "capability_scores" in judge
    assert "Earlier comparable trace" in judge
    assert "complete_failure_inventory" in judge
    assert "reporting_boundary" in judge
    assert "client_identity_resolution" in judge
    assert "complete_log_retrieval" in judge
    assert "orchestration_structure" in judge
    assert "leaf_delegation" in judge
    assert "follow_up_actionability" in judge
    assert "Case applicability" in judge
    assert "marked false is not applicable" in judge


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
