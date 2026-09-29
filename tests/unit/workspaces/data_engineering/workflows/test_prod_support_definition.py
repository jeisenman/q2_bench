from workspaces.data_engineering.workflows.prod_support.definition import (
    PRODUCTION_SUPPORT_DEFINITION,
    PRODUCTION_SUPPORT_NAME,
)

EXPECTED_TOOLS = {
    "inspect_cluster_health",
    "discover_airflow_failures",
    "inspect_airflow_workload",
    "query_oms_job",
    "fetch_airflow_task_log",
    "classify_failure",
    "trigger_resource_discovery_agent",
    "execute_airflow_retries",
}


def test_definition_declares_tools_not_delegates() -> None:
    # The in-process orchestrator and its subagents are gone: the harness runs
    # the loop from the production-support skill, and the workflow exposes a
    # flat set of tools with no delegation.
    assert {tool.name for tool in PRODUCTION_SUPPORT_DEFINITION.tools} == EXPECTED_TOOLS
    assert not any(
        tool.name.startswith("DelegateTo")
        for tool in PRODUCTION_SUPPORT_DEFINITION.tools
    )
    assert PRODUCTION_SUPPORT_DEFINITION.can_delegate is False
    assert PRODUCTION_SUPPORT_DEFINITION.version == "1"


def test_definition_points_at_the_skill_not_a_persona() -> None:
    assert PRODUCTION_SUPPORT_NAME == "production-support"
    assert PRODUCTION_SUPPORT_DEFINITION.name == PRODUCTION_SUPPORT_NAME
    assert "skills/prod-support" in PRODUCTION_SUPPORT_DEFINITION.instructions
    assert "no model selects" in PRODUCTION_SUPPORT_DEFINITION.instructions
    assert "You are" not in PRODUCTION_SUPPORT_DEFINITION.instructions
