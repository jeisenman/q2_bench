"""Runnable stdio MCP server for the production-support agent."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from mcp.server.mcpserver import MCPServer

from agentsdk.domain import AgentRequest
from agentsdk.ws.data_engineering.agents.prod_support import (
    AirflowFailure,
    AirflowFailureSource,
    ProdSupportAgent,
    ReplayAirflowFailureSource,
)

SERVER_NAME = "prod-support"
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
    dataset = os.environ.get("PROD_SUPPORT_DATASET")
    if dataset:
        return ReplayAirflowFailureSource(Path(dataset))
    return EmptyAirflowFailureSource()


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
    result = await agent.run(
        AgentRequest(
            prompt=prompt,
            correlation_id=correlation_id or uuid4().hex,
            attributes=attributes,
        )
    )
    return {
        "output": result.output,
        "correlation_id": result.correlation_id,
        "tool_calls": result.tool_calls,
        "attributes": dict(result.attributes),
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
