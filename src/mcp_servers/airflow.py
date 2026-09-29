"""Read-only Airflow capability MCP server."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Any

from mcp.server.mcpserver import MCPServer

from adapters.airflow import AirflowApiSource
from adapters.mcp import airflow_failure_from_payload, airflow_failure_payload
from adapters.telemetry import configure_telemetry
from workspaces.data_engineering.workflows.prod_support import Region

SERVER_NAME = "airflow-capabilities"
server = MCPServer(
    SERVER_NAME,
    description="Read-only Airflow evidence capabilities.",
)


@lru_cache(maxsize=1)
def _source() -> AirflowApiSource:
    return AirflowApiSource.from_environment()


@server.tool(
    name="list_failed_task_instances",
    description="List failed Airflow task instances ending after a UTC cutoff.",
)
async def list_failed_task_instances(
    since: str,
    region: str | None = None,
) -> dict[str, object]:
    """Return exact failed task identities without task-log bodies."""
    cutoff = _datetime(since)
    source = _source()
    failures = (
        await source.discover_region_failures(Region(region), cutoff)
        if region is not None
        else await source.discover_failures(cutoff)
    )
    return {
        "failures": [airflow_failure_payload(failure) for failure in failures],
        "count": len(failures),
    }


@server.tool(
    name="get_task_log",
    description="Read the exact Airflow log for one task instance and attempt.",
)
async def get_task_log(failure: dict[str, Any]) -> dict[str, object]:
    """Return one exact task log."""
    parsed = airflow_failure_from_payload(failure)
    return {"failure_id": parsed.failure_id, "log": await _source().fetch_log(parsed)}


@server.tool(
    name="has_task_success",
    description="Check for a same-DAG same-task success in a bounded window.",
)
async def has_task_success(
    failure: dict[str, Any],
    start_at: str,
    end_at: str,
) -> dict[str, object]:
    """Return a bounded recovery check."""
    parsed = airflow_failure_from_payload(failure)
    recovered = await _source().has_success_within(
        parsed,
        _datetime(start_at),
        _datetime(end_at),
    )
    return {"failure_id": parsed.failure_id, "has_success": recovered}


@server.tool(
    name="get_task_metadata",
    description="Read exact Airflow task operator metadata for workload routing.",
)
async def get_task_metadata(failure: dict[str, Any]) -> dict[str, object]:
    """Return allowlisted task metadata."""
    parsed = airflow_failure_from_payload(failure)
    metadata = await _source().fetch_task_metadata(parsed)
    return {
        "dag_id": metadata.dag_id,
        "task_id": metadata.task_id,
        "operator_name": metadata.operator_name,
    }


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        message = "timezone required"
        raise ValueError(message)
    return parsed


def main() -> None:
    """Run the read-only Airflow MCP server over stdio."""
    configure_telemetry(default_service_name=SERVER_NAME)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
