import asyncio
from typing import Any

import pytest

from agentsdk.domain import AgentDefinition, AgentRequest, AgentResult
from agentsdk.mcp_servers import (
    AgentMcpBinding,
    AgentMcpCatalog,
    McpPrompt,
    McpTool,
    bind_workspace_agent,
)


async def run_agent(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"result": arguments["request"]}


def test_catalog_exposes_imported_agent_capabilities() -> None:
    binding = AgentMcpBinding(
        agent_id="prod_support",
        tools=(McpTool("diagnose_pipeline", "Diagnose a failure.", run_agent),),
        prompts=(
            McpPrompt(
                "triage_incident",
                "Build a triage prompt.",
                lambda values: f"Triage {values['incident']}",
            ),
        ),
    )

    catalog = AgentMcpCatalog((binding,))

    assert catalog.tools["diagnose_pipeline"].description == "Diagnose a failure."
    assert (
        catalog.prompts["triage_incident"].render({"incident": "DE-1"}) == "Triage DE-1"
    )


def test_catalog_rejects_duplicate_capabilities() -> None:
    tool = McpTool("duplicate", "Duplicate.", run_agent)
    bindings = (
        AgentMcpBinding(agent_id="one", tools=(tool,)),
        AgentMcpBinding(agent_id="two", tools=(tool,)),
    )

    with pytest.raises(ValueError, match="Duplicate MCP tool"):
        AgentMcpCatalog(bindings)


class FakeWorkspaceAgent:
    @property
    def definition(self) -> AgentDefinition:
        return AgentDefinition(
            name="prod_support",
            description="Triage production pipeline incidents.",
            instructions="Use evidence from the incident.",
        )

    async def run(self, request: AgentRequest) -> AgentResult:
        return AgentResult(
            output=f"triaged: {request.prompt}",
            correlation_id=request.correlation_id,
        )


def test_workspace_agent_binding_exposes_tool_resource_and_prompt() -> None:
    binding = bind_workspace_agent(FakeWorkspaceAgent())

    result = asyncio.run(
        binding.tools[0].handler(
            {"prompt": "pipeline failed", "correlation_id": "incident-1"}
        )
    )

    assert result["output"] == "triaged: pipeline failed"
    assert (
        asyncio.run(binding.resources[0].reader())
        == "Triage production pipeline incidents."
    )
    assert "Request: pipeline failed" in binding.prompts[0].render(
        {"request": "pipeline failed"}
    )
