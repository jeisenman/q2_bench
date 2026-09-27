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
    description="Check DAG parsing and classify production Airflow failures.",
    instructions=(
        "Use the supplied operational date and US, CA, or combined scope. Query "
        "selected regions concurrently. For each region, return DAG-processor health, "
        "the active DAG count, and every direct validated error under an exact "
        "'For <region> Cluster the following errors exist:' heading. Preserve the "
        "region attached by the source and never move an error between headings. "
        "Read parsing health "
        "from Airflow health and DAG inventory; never infer it from failed tasks. Do "
        "not triage configured D2P or MI3 omissions. Do not delegate or mutate "
        "production."
    ),
    tools=(
        DISCOVER_FAILURES,
        FETCH_TASK_LOG,
        INSPECT_WORKLOAD,
        QUERY_OMS_JOB,
        CLASSIFY_FAILURE,
    ),
    version="3",
)
