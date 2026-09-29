"""Public definition for the production-support workflow.

The workflow is one deterministic composition of tools. The agent loop that
drives it belongs to the harness, which follows the `production-support`
skill and reaches these tools through the `prod-support` MCP server.
"""

from __future__ import annotations

from domain import AgentDefinition
from workspaces.data_engineering.workflows.prod_support.tools import (
    CLASSIFY_FAILURE,
    DISCOVER_FAILURES,
    EXECUTE_AIRFLOW_RETRIES,
    FETCH_TASK_LOG,
    INSPECT_CLUSTER_HEALTH,
    INSPECT_WORKLOAD,
    QUERY_OMS_JOB,
    TRIGGER_RESOURCE_DISCOVERY,
)

PRODUCTION_SUPPORT_NAME = "production-support"
PRODUCTION_SUPPORT_SKILL = "src/workspaces/data_engineering/skills/prod-support"
PRODUCTION_SUPPORT_DEFINITION = AgentDefinition(
    name=PRODUCTION_SUPPORT_NAME,
    description=(
        "Discover, triage, and report production Airflow failures for one "
        "operational day across US and CA, and execute authorized reruns."
    ),
    instructions=(
        "Deterministic workflow. Control flow is fixed and no model selects "
        f"the next step. The operating procedure lives in {PRODUCTION_SUPPORT_SKILL}."
    ),
    tools=(
        INSPECT_CLUSTER_HEALTH,
        DISCOVER_FAILURES,
        INSPECT_WORKLOAD,
        QUERY_OMS_JOB,
        FETCH_TASK_LOG,
        CLASSIFY_FAILURE,
        TRIGGER_RESOURCE_DISCOVERY,
        EXECUTE_AIRFLOW_RETRIES,
    ),
)
