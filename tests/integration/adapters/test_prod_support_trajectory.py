from workspaces.data_engineering.benchmarks import (
    ToolStep,
    build_efficiency_judge_prompt,
    evaluate_trajectory,
)

BROAD_QUERY_SCORE = 0.25


def direct_steps() -> tuple[ToolStep, ...]:
    return (
        ToolStep.create("discover_airflow_failures", failed_since="cutoff"),
        ToolStep.create("fetch_airflow_task_log", failure_id="failure"),
        ToolStep.create(
            "query_oms_job",
            table="DI_Scheduling_CL",
            client_id_g="client",
            run_id_s="run",
            task_id_s="task",
            try_number_d=4,
        ),
        ToolStep.create("classify_failure", failure_id="failure"),
    )


def test_direct_oms_trajectory_receives_full_efficiency_score() -> None:
    score = evaluate_trajectory(direct_steps())

    assert score.chain_complete
    assert score.direct_oms_lookup
    assert score.efficiency == 1.0
    assert score.violations == ()


def test_broad_oms_search_is_penalized_deterministically() -> None:
    broad = (
        *direct_steps()[:2],
        ToolStep.create(
            "query_oms_job",
            table="ApplicationLog2_CL",
            search="client",
            query_all_tables=True,
        ),
        direct_steps()[-1],
    )

    score = evaluate_trajectory(broad)

    assert not score.direct_oms_lookup
    assert score.broad_query_count == 1
    assert score.efficiency == BROAD_QUERY_SCORE
    assert "broad search" in " ".join(score.violations)


def test_llm_judge_prompt_cannot_excuse_inefficient_queries() -> None:
    prompt = build_efficiency_judge_prompt(direct_steps())

    assert "DI_Scheduling_CL" in prompt
    assert "client_id_g" in prompt
    assert "Punish broad search" in prompt
    assert "cannot override deterministic violations" in prompt
