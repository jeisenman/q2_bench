import pytest

from workspaces.data_engineering.agents.production_support import (
    AIRFLOW_AGENT_NAME,
    BENCH_BUILDER_NAME,
    CLUSTER_AGENT_NAME,
    FOLLOW_UP_AGENT_NAME,
    ORCHESTRATOR_NAME,
    REPORTER_NAME,
    TRIAGE_AGENT_NAME,
    build_production_support_suite,
)


def test_suite_contains_orchestrator_and_six_subagents() -> None:
    suite = build_production_support_suite()

    assert tuple(definition.name for definition in suite.definitions) == (
        ORCHESTRATOR_NAME,
        CLUSTER_AGENT_NAME,
        AIRFLOW_AGENT_NAME,
        TRIAGE_AGENT_NAME,
        FOLLOW_UP_AGENT_NAME,
        REPORTER_NAME,
        BENCH_BUILDER_NAME,
    )
    assert suite.orchestrator.can_delegate is True
    assert suite.bench_builder_agent.can_delegate is True
    assert all(
        subagent.can_delegate is False
        for subagent in suite.subagents
        if subagent.name != BENCH_BUILDER_NAME
    )


def test_orchestrator_delegates_only_to_declared_subagents() -> None:
    suite = build_production_support_suite()

    assert {tool.name for tool in suite.orchestrator.tools} == {
        "run_prod_support",
        "DelegateToClusterAgent",
        "DelegateToAirflowAgent",
        "DelegateToTriageAgent",
        "DelegateToFollowUpAgent",
        "DelegateToReporter",
        "DelegateToBenchBuilderAgent",
    }
    assert "Default to both CA and US" in suite.orchestrator.instructions
    assert "SERVE THE SAME REPORT TO THE END USER" in suite.orchestrator.instructions
    assert "Do prod support for yesterday" in suite.orchestrator.instructions
    assert "follow_up_message" in suite.orchestrator.instructions
    assert "Do you approve these re-runs?" in suite.orchestrator.instructions
    assert "Slack-friendly mrkdwn" in suite.orchestrator.instructions
    assert "GitHub-style `#` headings" in suite.orchestrator.instructions


def test_specialists_have_explicit_scoped_prompts_and_tools() -> None:
    suite = build_production_support_suite()

    assert {tool.name for tool in suite.cluster_agent.tools} == {
        "inspect_cluster_health"
    }
    assert {tool.name for tool in suite.airflow_agent.tools} == {
        "classify_failure",
        "discover_airflow_failures",
        "fetch_airflow_task_log",
        "inspect_airflow_workload",
        "query_oms_job",
        "trigger_resource_discovery_agent",
    }
    assert {tool.name for tool in suite.follow_up_agent.tools} == {
        "execute_airflow_retries",
        "plan_airflow_retries",
    }
    assert suite.triage_agent.tools == ()
    assert {tool.name for tool in suite.bench_builder_agent.tools} >= {
        "DelegateToClusterAgent",
        "DelegateToAirflowAgent",
        "DelegateToTriageAgent",
        "DelegateToFollowUpAgent",
        "DelegateToReporter",
        "WriteDailyBenchmarkCase",
    }
    assert suite.reporter.tools == ()
    assert "Never treat missing evidence as proof" in suite.cluster_agent.instructions
    assert "explicit terminal evidence" in suite.airflow_agent.instructions
    assert "complete client UUID to Resource Discovery" in (
        suite.airflow_agent.instructions
    )
    resource_tool = next(
        tool
        for tool in suite.airflow_agent.tools
        if tool.name == "trigger_resource_discovery_agent"
    )
    assert resource_tool.input_schema == (("client_id", "complete UUID string"),)
    assert "three-character prefixes are report-only" in resource_tool.description
    assert "explicitly authorized Airflow task instances" in (
        suite.follow_up_agent.instructions
    )
    assert "at most once per delegated request" in suite.follow_up_agent.instructions
    assert "Compliant candidate example:" in suite.follow_up_agent.instructions
    assert "Non-compliant candidate example:" in suite.follow_up_agent.instructions
    assert "check-for-subscriber-client-errors" in (suite.follow_up_agent.instructions)
    assert "log_cleanup: expire-logs-3" in suite.follow_up_agent.instructions
    assert "Andi Application Owner (621): MI3" in (suite.follow_up_agent.instructions)
    assert "# Prod Support Report" in suite.reporter.instructions
    assert "Message for developer:" in suite.reporter.instructions
    assert ":bangbang: PROD SUPPORT" in suite.reporter.instructions
    assert "Follow Ups:" in suite.reporter.instructions
    assert "validate_event_bus_opportunities" in suite.reporter.instructions
    assert "validate-event-bus-opportunities" in suite.reporter.instructions


def test_suite_accepts_per_agent_model_overrides() -> None:
    suite = build_production_support_suite(
        models={
            ORCHESTRATOR_NAME: "orchestrator-model",
            AIRFLOW_AGENT_NAME: "airflow-model",
            FOLLOW_UP_AGENT_NAME: "follow-up-model",
        }
    )

    assert suite.orchestrator.model == "orchestrator-model"
    assert suite.airflow_agent.model == "airflow-model"
    assert suite.follow_up_agent.model == "follow-up-model"
    assert suite.cluster_agent.model is None
    assert suite.reporter.model is None


def test_suite_rejects_empty_model_override() -> None:
    with pytest.raises(ValueError, match="model for Reporter must not be empty"):
        build_production_support_suite(models={REPORTER_NAME: " "})
