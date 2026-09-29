"""Runnable stdio MCP server for warehouse reads and Cortex inference.

Two routes, both environment-aware. ``run_warehouse_query`` is deterministic
by contract: it is read-only, it rejects anything that cannot mean the same
thing in every backend, and in the sandbox it is served by DuckDB over CSV
fixtures. ``run_cortex_complete`` is explicitly not deterministic outside the
sandbox, and says so in every response.
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.mcpserver import MCPServer

from adapters.warehouse_resolution import (
    configured_environment,
    resolve_cortex,
    resolve_warehouse,
)
from domain.environments import Environment
from domain.sql_portability import SqlPortabilityError
from observability import current_trace_metadata, traced_operation
from ports.cortex import CortexRequest
from ports.secrets import SecretProvider
from ports.warehouse import QueryResult, SqlStatement

SERVER_NAME = "warehouse"
MAX_ROWS = 1000
server = MCPServer(
    SERVER_NAME,
    description="Deterministic warehouse reads and Cortex inference by environment.",
)


class EnvironmentSecrets:
    """Resolve a Snowflake credential from the process environment.

    Secret references map to environment variables so a local run needs no
    secret manager. The value is read at call time and never stored.
    """

    async def get_secret(self, name: str) -> str:
        """Return a secret value or raise when it is unavailable."""
        variable = name.replace("/", "_").replace("-", "_").upper()
        value = os.environ.get(variable, "").strip()
        if not value:
            message = f"secret {name!r} is not set; export {variable}"
            raise LookupError(message)
        return value


def _secrets() -> SecretProvider:
    return EnvironmentSecrets()


def _environment(requested: str | None) -> Environment:
    if requested is None or not requested.strip():
        return configured_environment()
    return Environment.parse(requested)


def _render(result: QueryResult, *, truncated: bool) -> dict[str, Any]:
    return {
        "environment": result.environment.value,
        "deterministic": result.environment.is_deterministic,
        "columns": [
            {"name": column.name, "type": column.type_name} for column in result.columns
        ],
        "rows": [list(row) for row in result.rows],
        "row_count": len(result.rows),
        "truncated": truncated,
        "trace": current_trace_metadata(),
    }


@server.tool(
    name="run_warehouse_query",
    description=(
        "Run one read-only, portable SQL statement against dev, stage, prod, or "
        "the deterministic sandbox. Parameters are bound, not interpolated. "
        "Statements that cannot mean the same thing in every backend are "
        "rejected with the portable form to use instead."
    ),
)
async def run_warehouse_query(
    statement: str,
    parameters: dict[str, Any] | None = None,
    environment: str | None = None,
) -> dict[str, Any]:
    """Return rows for one portable statement in the resolved environment."""
    resolved = _environment(environment)
    async with traced_operation(
        "mcp.run_warehouse_query",
        attributes={
            "q2.mcp.tool.name": "run_warehouse_query",
            "q2.warehouse.environment": resolved.value,
        },
    ):
        warehouse = resolve_warehouse(resolved, _secrets())
        try:
            result = await warehouse.fetch(
                SqlStatement(text=statement, parameters=parameters or {})
            )
        except SqlPortabilityError as error:
            return {
                "environment": resolved.value,
                "error": "not_portable",
                "message": str(error),
                "violations": list(error.violations),
            }
        truncated = len(result.rows) > MAX_ROWS
        if truncated:
            result = QueryResult(
                columns=result.columns,
                rows=result.rows[:MAX_ROWS],
                environment=result.environment,
            )
        return _render(result, truncated=truncated)


@server.tool(
    name="run_cortex_complete",
    description=(
        "Run one Snowflake Cortex completion in dev, stage, or prod. In the "
        "sandbox this replays a recorded response and fails when none exists. "
        "Cortex is model inference: results are not reproducible outside the "
        "sandbox, and every response reports which case applied."
    ),
)
async def run_cortex_complete(
    model: str,
    prompt: str,
    environment: str | None = None,
) -> dict[str, Any]:
    """Return one Cortex completion from the resolved environment."""
    resolved = _environment(environment)
    async with traced_operation(
        "mcp.run_cortex_complete",
        attributes={
            "q2.mcp.tool.name": "run_cortex_complete",
            "q2.warehouse.environment": resolved.value,
            "q2.cortex.model": model,
        },
    ):
        cortex = resolve_cortex(resolved, _secrets())
        response = await cortex.complete(CortexRequest(model=model, prompt=prompt))
        return {
            "environment": response.environment.value,
            "model": response.model,
            "completion": response.text,
            "recorded": response.recorded,
            "deterministic": response.recorded,
            "trace": current_trace_metadata(),
        }


@server.tool(
    name="describe_warehouse_table",
    description=(
        "List the typed columns of one table in the resolved environment. In "
        "the sandbox these are the declared fixture columns, which mirror the "
        "real warehouse schema."
    ),
)
async def describe_warehouse_table(
    schema: str,
    table: str,
    environment: str | None = None,
) -> dict[str, Any]:
    """Return the typed columns of one table."""
    resolved = _environment(environment)
    warehouse = resolve_warehouse(resolved, _secrets())
    columns = await warehouse.columns(schema, table)
    return {
        "environment": resolved.value,
        "schema": schema,
        "table": table,
        "columns": [
            {"name": column.name, "type": column.type_name} for column in columns
        ],
    }


def main() -> None:
    """Run the warehouse MCP server over stdio."""
    server.run()


if __name__ == "__main__":
    main()
