"""Tool definitions exposed by the production-support agent."""

from domain import ToolDefinition

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
QUERY_OMS_JOB = ToolDefinition(
    name="query_oms_job",
    description=(
        "Query DI_Scheduling_CL directly for one Spark job using its exact "
        "client, run, task, and try identifiers."
    ),
    input_schema=(
        ("client_id_g", "string"),
        ("run_id_s", "string"),
        ("task_id_s", "string"),
        ("try_number_d", "integer"),
    ),
)
