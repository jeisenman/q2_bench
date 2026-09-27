"""Tool definitions exposed by the production-support agent."""

from domain import ToolDefinition

RUN_PROD_SUPPORT_MCP = ToolDefinition(
    name="run_prod_support",
    description=(
        "Run the production-support MCP workflow for the resolved operational day "
        "and return links plus developer, Data Internal, and follow-up messages."
    ),
    input_schema=(("prompt", "string"),),
)
INSPECT_CLUSTER_HEALTH = ToolDefinition(
    name="inspect_cluster_health",
    description=(
        "Run the read-only cluster health check for selected regions and return "
        "pod state, restart counts, and KEDA status."
    ),
    input_schema=(("regions", "array"),),
)
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
INSPECT_WORKLOAD = ToolDefinition(
    name="inspect_airflow_workload",
    description=(
        "Read exact Airflow task metadata and classify the operator as Spark "
        "batch, container batch, or other before choosing an evidence source."
    ),
    input_schema=(("dag_id", "string"), ("task_id", "string")),
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
        ("region", "string"),
        ("table", "string"),
        ("client_id_g", "string"),
        ("run_id_s", "string"),
        ("task_id_s", "string"),
        ("try_number_d", "integer"),
        ("start_at", "datetime"),
    ),
)
TRIGGER_RESOURCE_DISCOVERY = ToolDefinition(
    name="trigger_resource_discovery_agent",
    description=(
        "Invoke the read-only Resource Discovery agent for a resend client's "
        "provisioned client identifier."
    ),
    input_schema=(("client_id", "string"),),
)
PLAN_AIRFLOW_RETRIES = ToolDefinition(
    name="plan_airflow_retries",
    description=(
        "Dry-run exact regional Airflow retry targets selected from the prior "
        "production-support failure inventory."
    ),
    input_schema=(("direction", "string"), ("candidates", "array")),
)
EXECUTE_AIRFLOW_RETRIES = ToolDefinition(
    name="execute_airflow_retries",
    description=(
        "Execute an unchanged validated Airflow retry plan after exact approval."
    ),
    input_schema=(("plan_id", "string"), ("approval_id", "string")),
)
