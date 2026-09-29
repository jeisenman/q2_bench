"""OMS read capability adapters backed by MCP tools."""

from __future__ import annotations

from datetime import datetime

from adapters.mcp.client import McpToolCaller
from workspaces.data_engineering.agents.oms_agent import (
    OmsEnvironment,
    OmsJobQueryParameters,
    OmsQuery,
    OmsQueryResult,
    OmsRegion,
    OmsWorkspace,
    resolve_workspace,
)


class OmsMcpError(RuntimeError):
    """Raised when an OMS MCP result violates its typed contract."""

    @classmethod
    def unknown_workspace(cls, workspace: OmsWorkspace) -> OmsMcpError:
        """Return an error for a workspace outside the configured allowlist."""
        return cls(f"OMS MCP workspace is not configured: {workspace.name}")

    @classmethod
    def invalid_result(cls) -> OmsMcpError:
        """Return an error for malformed query results."""
        return cls("OMS MCP query result must contain columns and rows")

    @classmethod
    def invalid_evidence(cls) -> OmsMcpError:
        """Return an error for malformed job evidence."""
        return cls("OMS MCP job evidence must be text")


class OmsMcpSource:
    """Implement OMS query and exact-job protocols through MCP."""

    def __init__(self, caller: McpToolCaller) -> None:
        """Initialize with an injected MCP tool caller."""
        self._caller = caller

    async def query(
        self,
        workspace: OmsWorkspace,
        query: OmsQuery,
    ) -> OmsQueryResult:
        """Execute one bounded query through the read-only OMS server."""
        environment, region = _route(workspace)
        result = await self._caller.call_tool(
            "query_oms",
            {
                "environment": environment.value,
                "region": region.value,
                "kql": query.kql,
                "timespan": query.timespan,
            },
        )
        columns = result.get("columns")
        rows = result.get("rows")
        if not isinstance(columns, list) or not isinstance(rows, list):
            raise OmsMcpError.invalid_result()
        if not all(isinstance(column, str) for column in columns):
            raise OmsMcpError.invalid_result()
        if not all(isinstance(row, list) for row in rows):
            raise OmsMcpError.invalid_result()
        return OmsQueryResult(
            columns=tuple(columns),
            rows=tuple(tuple(row) for row in rows),
        )

    async def query_job(self, parameters: OmsJobQueryParameters) -> str:
        """Return bounded exact-job evidence."""
        result = await self._caller.call_tool(
            "query_job_evidence",
            {
                "parameters": {
                    "region": getattr(
                        parameters.region,
                        "value",
                        str(parameters.region),
                    ),
                    "client_id_g": parameters.client_id_g,
                    "run_id_s": parameters.run_id_s,
                    "task_id_s": parameters.task_id_s,
                    "try_number_d": parameters.try_number_d,
                    "start_at": _timestamp(parameters.start_at),
                    "table": parameters.table,
                }
            },
        )
        evidence = result.get("evidence")
        if not isinstance(evidence, str):
            raise OmsMcpError.invalid_evidence()
        return evidence


def _route(workspace: OmsWorkspace) -> tuple[OmsEnvironment, OmsRegion]:
    for environment in OmsEnvironment:
        for region in OmsRegion:
            try:
                configured = resolve_workspace(environment, region)
            except ValueError:
                continue
            if configured == workspace:
                return environment, region
    raise OmsMcpError.unknown_workspace(workspace)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        message = "timezone required"
        raise ValueError(message)
    return value.isoformat()
