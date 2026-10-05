"""Read-only remote-data queries and notebook generation over MCP."""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any

from mcp.server.mcpserver import MCPServer

from adapters.databricks import (
    DatabricksRunRequest,
    submit_databricks_run,
    upload_integration_branch,
)
from adapters.outbound.data_engineering import (
    ADLS_TARGETS,
    DATABRICKS_TARGETS,
    OMS_TARGETS,
    SNOWFLAKE_TARGETS,
    SnowflakeEnvironment,
)
from adapters.telemetry import configure_telemetry
from mcp_servers.remote_data_notebooks import (
    build_adls_notebook,
    build_databricks_notebook,
    build_snowflake_notebook,
)
from mcp_servers.remote_data_oms import execute_job_evidence, execute_oms_query

SERVER_NAME = "remote-data"
DEFAULT_SNOWFLAKE_ENVIRONMENT = SnowflakeEnvironment.PROD_US.value
server = MCPServer(
    SERVER_NAME,
    description="Build read-only query notebooks and query approved remote data.",
)


@server.tool(
    name="list_remote_data_targets",
    description="List the non-secret Databricks, ADLS, Snowflake, and OMS allowlists.",
)
async def list_remote_data_targets() -> dict[str, object]:
    """Return every configured non-secret remote-data target."""
    return {
        "databricks": {
            name: {
                "name": target.name,
                "workspace_id": target.workspace_id,
                "sql_warehouse_id": target.sql_warehouse_id,
            }
            for name, target in DATABRICKS_TARGETS.items()
        },
        "adls": {
            environment.value: target.account_name
            for environment, target in ADLS_TARGETS.items()
        },
        "snowflake": [
            {
                "environment": target.environment.value,
                "access_modes": sorted(mode.value for mode in target.access_modes),
            }
            for target in SNOWFLAKE_TARGETS
        ],
        "oms": {
            region.value: target.workspace_name
            for region, target in OMS_TARGETS.items()
        },
    }


@server.tool(
    name="make_databricks_notebook",
    description="Build Databricks source boilerplate for Data Engineering or RA.",
)
async def make_databricks_notebook(
    platform: str,
    code: str,
) -> dict[str, object]:
    """Return a Databricks source notebook without executing it."""
    notebook = build_databricks_notebook(platform, code)
    return {
        "target": notebook.target,
        "format": "SOURCE",
        "source": notebook.source,
        "source_sha256": hashlib.sha256(notebook.source.encode()).hexdigest(),
    }


@server.tool(
    name="run_databricks_notebook",
    description=(
        "Submit an exact reviewed Databricks SOURCE notebook to an approved "
        "existing cluster."
    ),
)
async def run_databricks_notebook(
    platform: str,
    source: str,
    source_sha256: str,
    existing_cluster_id: str,
    options: dict[str, Any] | None = None,
) -> dict[str, object]:
    """Import and trigger one reviewed Databricks notebook run."""
    settings = options or {}
    unknown_options = sorted(set(settings) - {"run_name", "timeout_seconds"})
    if unknown_options:
        message = f"unsupported options: {', '.join(unknown_options)}"
        raise ValueError(message)
    run_name = settings.get("run_name", "remote-data-mcp")
    timeout_seconds = settings.get("timeout_seconds", 3_600)
    if not isinstance(run_name, str):
        message = "options.run_name must be a string"
        raise TypeError(message)
    if not isinstance(timeout_seconds, int):
        message = "options.timeout_seconds must be an integer"
        raise TypeError(message)
    submitted = await asyncio.to_thread(
        submit_databricks_run,
        DatabricksRunRequest(
            platform=platform,
            source=source,
            source_sha256=source_sha256,
            existing_cluster_id=existing_cluster_id,
            run_name=run_name,
            timeout_seconds=timeout_seconds,
        ),
    )
    return {
        "target": submitted.target,
        "notebook_path": submitted.notebook_path,
        "run_id": submitted.run_id,
        "source_sha256": submitted.source_sha256,
        "status": "submitted",
    }


@server.tool(
    name="upload_databricks_integration_branch",
    description=(
        "Run the local dsint helper to upload master/main or one RA-#### branch "
        "to the Data Science integration-testing workspace."
    ),
)
async def upload_databricks_integration_branch(branch: str) -> dict[str, object]:
    """Upload one explicitly selected branch without returning credentials."""
    uploaded = await asyncio.to_thread(upload_integration_branch, branch)
    return {
        "branch": uploaded.branch,
        "notebook_path": uploaded.notebook_path,
        "output": uploaded.output,
        "credential_requirements": [
            "DE_DATABRICKS_HOST",
            "DE_DATABRICKS_TOKEN",
        ],
        "status": "uploaded",
    }


@server.tool(
    name="make_adls_notebook",
    description="Build a bounded read-only Spark notebook for an ADLS location.",
)
async def make_adls_notebook(
    environment: str,
    container: str,
    path: str,
    file_format: str = "parquet",
    limit: int = 100,
) -> dict[str, object]:
    """Return an ADLS query notebook without executing it."""
    notebook = build_adls_notebook(
        environment,
        container,
        path,
        file_format,
        limit,
    )
    return {"target": notebook.target, "format": "SOURCE", "source": notebook.source}


@server.tool(
    name="make_snowflake_notebook",
    description=(
        "Build a bounded read-only Snowflake connector notebook. Defaults to "
        "US production when no environment is provided."
    ),
)
async def make_snowflake_notebook(
    statement: str,
    environment: str = DEFAULT_SNOWFLAKE_ENVIRONMENT,
    limit: int = 100,
) -> dict[str, object]:
    """Return a Snowflake query notebook, defaulting to US production."""
    notebook = build_snowflake_notebook(environment, statement, limit)
    return {"target": notebook.target, "format": "SOURCE", "source": notebook.source}


@server.tool(
    name="query_oms",
    description="Run bounded KQL against one allowlisted OMS workspace.",
)
async def query_oms(
    environment: str,
    region: str,
    kql: str,
    timespan: str,
) -> dict[str, object]:
    """Return raw tabular OMS results without classification."""
    return await execute_oms_query(environment, region, kql, timespan)


@server.tool(
    name="query_job_evidence",
    description="Read exact bounded production OMS evidence for one workload attempt.",
)
async def query_job_evidence(parameters: dict[str, Any]) -> dict[str, object]:
    """Return raw exact-job OMS evidence without classification."""
    return await execute_job_evidence(parameters)


def main() -> None:
    """Run the remote-data MCP server over stdio."""
    configure_telemetry(default_service_name=SERVER_NAME)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
