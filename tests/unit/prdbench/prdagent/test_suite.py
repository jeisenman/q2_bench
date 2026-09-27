import pytest

from prdbench.prdagent import (
    AIRFLOW_AGENT_NAME,
    CLUSTER_AGENT_NAME,
    ORCHESTRATOR_NAME,
    REPORTER_NAME,
    build_prd_agent_suite,
)


def test_suite_contains_orchestrator_and_three_subagents() -> None:
    suite = build_prd_agent_suite()

    assert tuple(definition.name for definition in suite.definitions) == (
        ORCHESTRATOR_NAME,
        CLUSTER_AGENT_NAME,
        AIRFLOW_AGENT_NAME,
        REPORTER_NAME,
    )
    assert suite.orchestrator.can_delegate is True
    assert all(subagent.can_delegate is False for subagent in suite.subagents)


def test_orchestrator_delegates_only_to_declared_subagents() -> None:
    suite = build_prd_agent_suite()

    assert {tool.name for tool in suite.orchestrator.tools} == {
        "DelegateToClusterAgent",
        "DelegateToAirflowAgent",
        "DelegateToReporter",
    }
    assert "smallest complete task" in suite.orchestrator.instructions
    assert "send only evidence-qualified findings to Reporter" in (
        suite.orchestrator.instructions
    )


def test_specialists_have_explicit_scoped_prompts_and_tools() -> None:
    suite = build_prd_agent_suite()

    assert {tool.name for tool in suite.cluster_agent.tools} == {"InspectClusterHealth"}
    assert {tool.name for tool in suite.airflow_agent.tools} == {
        "ListFailedTaskInstances",
        "ReadTaskLog",
    }
    assert suite.reporter.tools == ()
    assert "absence of evidence is unknown" in suite.cluster_agent.instructions
    assert "explicit terminal evidence" in suite.airflow_agent.instructions
    assert "Accept only evidence-qualified findings" in suite.reporter.instructions


def test_suite_accepts_per_agent_model_overrides() -> None:
    suite = build_prd_agent_suite(
        models={
            ORCHESTRATOR_NAME: "orchestrator-model",
            AIRFLOW_AGENT_NAME: "airflow-model",
        }
    )

    assert suite.orchestrator.model == "orchestrator-model"
    assert suite.airflow_agent.model == "airflow-model"
    assert suite.cluster_agent.model is None
    assert suite.reporter.model is None


def test_suite_rejects_empty_model_override() -> None:
    with pytest.raises(ValueError, match="model for Reporter must not be empty"):
        build_prd_agent_suite(models={REPORTER_NAME: " "})
