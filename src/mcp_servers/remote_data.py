"""Read-only remote-data queries and notebook generation over MCP."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from adapters.outbound.data_engineering import (
    ADLS_TARGETS,
    DATABRICKS_TARGETS,
    OMS_TARGETS,
    SNOWFLAKE_TARGETS,
)
from adapters.telemetry import configure_telemetry
from mcp_servers.remote_data_notebooks import (
    build_adls_notebook,
    build_databricks_notebook,
    build_snowflake_notebook,
)
from mcp_servers.remote_data_oms import execute_job_evidence, execute_oms_query

SERVER_NAME = "remote-data"
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
    return {"target": notebook.target, "format": "SOURCE", "source": notebook.source}


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
    description="Build a bounded read-only Snowflake connector notebook.",
)
async def make_snowflake_notebook(
    environment: str,
    statement: str,
    limit: int = 100,
) -> dict[str, object]:
    """Return a Snowflake query notebook without executing it."""
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
