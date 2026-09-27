"""Concise definitions for the non-delegating prod-support components."""

from domain import AgentDefinition
from workspaces.data_engineering.agents.prod_support.tools import (
    CLASSIFY_FAILURE,
    DISCOVER_FAILURES,
    FETCH_TASK_LOG,
    INSPECT_CLUSTER_HEALTH,
    INSPECT_WORKLOAD,
    QUERY_OMS_JOB,
)

PROD_SUPPORT_CLUSTER_DEFINITION = AgentDefinition(
    name="prod-support.cluster",
    description="Check selected production cluster health.",
    instructions=(
        "Check the requested US, CA, or both clusters. Run the cluster health script "
        "and return pod state, restart count, and KEDA health. Do not delegate and do "
        "not mutate production."
    ),
    tools=(INSPECT_CLUSTER_HEALTH,),
    version="1",
)

PROD_SUPPORT_AIRFLOW_DEFINITION = AgentDefinition(
    name="prod-support.airflow",
    description="Find and classify selected production Airflow failures.",
    instructions=(
        "Use the supplied operational date and US, CA, or combined scope. Query "
        "selected regions concurrently and return direct validated errors. Do not "
        "triage configured D2P or MI3 omissions. Do not delegate or mutate production."
    ),
    tools=(
        DISCOVER_FAILURES,
        FETCH_TASK_LOG,
        INSPECT_WORKLOAD,
        QUERY_OMS_JOB,
        CLASSIFY_FAILURE,
    ),
    version="1",
)
