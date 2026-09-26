"""Runnable stdio MCP server for the production-support agent."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from mcp.server.mcpserver import MCPServer

from adapters.airflow import AirflowApiSource
from domain import AgentRequest
from workspaces.data_engineering.agents.prod_support import (
    AirflowFailure,
    AirflowFailureSource,
    ProdSupportAgent,
    ReplayAirflowFailureSource,
)

SERVER_NAME = "prod-support"
SOURCE_ENV = "PROD_SUPPORT_SOURCE"
DATASET_ENV = "PROD_SUPPORT_DATASET"
server = MCPServer(
    SERVER_NAME,
    description="Production-support tools for data-engineering incidents.",
)


class EmptyAirflowFailureSource:
    """Safe default source when no replay dataset is configured."""

    async def discover_failures(
        self,
        since: datetime,
    ) -> tuple[AirflowFailure, ...]:
        """Return no production failures."""
        del since
        return ()

    async def fetch_log(self, failure: AirflowFailure) -> str:
        """Return the embedded log when present."""
        return failure.log


def _source() -> AirflowFailureSource:
    source_mode = os.environ.get(SOURCE_ENV)
    dataset = os.environ.get(DATASET_ENV)
    if source_mode is None:
        return (
            ReplayAirflowFailureSource(Path(dataset))
            if dataset
            else EmptyAirflowFailureSource()
        )
    if source_mode == "production":
        if dataset:
            message = f"{DATASET_ENV} cannot be set when {SOURCE_ENV}=production"
            raise ValueError(message)
        return AirflowApiSource.from_environment()
    if source_mode == "replay":
        if not dataset:
            message = f"{DATASET_ENV} is required when {SOURCE_ENV}=replay"
            raise ValueError(message)
        return ReplayAirflowFailureSource(Path(dataset))
    if source_mode == "empty":
        if dataset:
            message = f"{DATASET_ENV} cannot be set when {SOURCE_ENV}=empty"
            raise ValueError(message)
        return EmptyAirflowFailureSource()
    message = (
        f"unsupported {SOURCE_ENV} value {source_mode!r}; "
        "expected production, replay, or empty"
    )
    raise ValueError(message)


agent = ProdSupportAgent(_source())


@server.tool(
    name="run_prod_support",
    description="Investigate a production data-engineering incident.",
)
async def run_prod_support(
    prompt: str,
    service: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Run the production-support agent with optional service context."""
    attributes = (("service", service),) if service else ()
    request = AgentRequest(
        prompt=prompt,
        correlation_id=correlation_id or uuid4().hex,
        attributes=attributes,
    )
    outcome = await agent.investigate(request.prompt)
    return {
        "output": outcome.report,
        "developer_report": outcome.developer_report,
        "data_internal_report": outcome.data_internal_report,
        "follow_up": outcome.follow_up,
        "correlation_id": request.correlation_id,
        "tool_calls": tuple(tool.name for tool in agent.definition.tools),
        "attributes": {
            **dict(request.attributes),
            "operational_date": outcome.operational_date.isoformat(),
            "failed_since": outcome.failed_since.isoformat(),
            "failure_count": len(outcome.failures),
        },
    }


@server.resource(
    "agent://prod-support/definition",
    name="prod-support definition",
    description="Framework-neutral definition of the prod-support agent.",
)
async def prod_support_definition() -> str:
    """Return the agent definition for MCP resource clients."""
    return agent.definition.description


@server.prompt(
    name="prod_support_request",
    description="Prepare a request for the prod-support agent.",
)
def prod_support_prompt(request: str) -> str:
    """Render the production-support instructions with a request."""
    return f"{agent.definition.instructions}\n\nRequest: {request}"


def main() -> None:
    """Run the MCP server over stdio."""
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
