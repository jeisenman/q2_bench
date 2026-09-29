"""Read-only OMS capability MCP server."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Any

from mcp.server.mcpserver import MCPServer

from adapters.oms import AzureLogAnalyticsSource, AzureOmsJobEvidenceSource
from adapters.telemetry import configure_telemetry
from workspaces.data_engineering.agents.oms_agent import (
    OmsEnvironment,
    OmsJobQueryParameters,
    OmsQuery,
    OmsRegion,
    resolve_workspace,
)

SERVER_NAME = "oms-capabilities"
server = MCPServer(
    SERVER_NAME,
    description="Read-only bounded OMS query capabilities.",
)


@lru_cache(maxsize=1)
def _query_source() -> AzureLogAnalyticsSource:
    return AzureLogAnalyticsSource.create()


@lru_cache(maxsize=1)
def _job_source() -> AzureOmsJobEvidenceSource:
    return AzureOmsJobEvidenceSource(_query_source())


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
    """Return JSON-compatible tabular OMS results."""
    workspace = resolve_workspace(OmsEnvironment(environment), OmsRegion(region))
    result = await _query_source().query(workspace, OmsQuery(kql, timespan))
    return {
        "workspace": workspace.name,
        "columns": list(result.columns),
        "rows": [[_json_value(value) for value in row] for row in result.rows],
    }


@server.tool(
    name="query_job_evidence",
    description="Read exact bounded production OMS evidence for one workload attempt.",
)
async def query_job_evidence(
    parameters: dict[str, Any],
) -> dict[str, object]:
    """Return deterministic exact-job evidence."""
    query_parameters = OmsJobQueryParameters(
        region=str(parameters["region"]),
        client_id_g=str(parameters["client_id_g"]),
        run_id_s=str(parameters["run_id_s"]),
        task_id_s=str(parameters["task_id_s"]),
        try_number_d=int(str(parameters["try_number_d"])),
        start_at=_datetime(str(parameters["start_at"])),
        table=str(parameters["table"]),
    )
    return {"evidence": await _job_source().query_job(query_parameters)}


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        message = "timezone required"
        raise ValueError(message)
    return parsed


def _json_value(value: object) -> object:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def main() -> None:
    """Run the read-only OMS MCP server over stdio."""
    configure_telemetry(default_service_name=SERVER_NAME)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
