"""Tool definitions exposed by the production-support agent."""

from agentsdk.domain import ToolDefinition

DISCOVER_FAILURES = ToolDefinition(
    name="discover_airflow_failures",
    description="Query failed Airflow task instances by end-date cutoff.",
    input_schema=(("failed_since", "datetime"),),
)
FETCH_TASK_LOG = ToolDefinition(
    name="fetch_airflow_task_log",
    description="Retrieve the exact log for one failed task instance.",
    input_schema=(("failure_id", "string"),),
)
CLASSIFY_FAILURE = ToolDefinition(
    name="classify_failure",
    description="Classify explicit failure evidence from a captured task log.",
    input_schema=(("failure_id", "string"), ("log", "string")),
)
