"""Framework-neutral composition values for exposing agents through MCP."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from domain import AgentRequest
from observability import (
    current_trace_metadata,
    extracted_trace_context,
    traced_operation,
)
from workspaces.data_engineering.agents.contracts import WorkspaceAgent
from workspaces.data_engineering.benchmarks import (
    benchmark_case_count,
    insufficient_benchmark_warning,
    prepend_benchmark_warning,
)

ToolHandler = Callable[[Mapping[str, Any]], Awaitable[Mapping[str, Any]]]
ResourceReader = Callable[[], Awaitable[str]]
PromptRenderer = Callable[[Mapping[str, str]], str]


@dataclass(frozen=True, slots=True)
class McpTool:
    """An agent operation exposed as an MCP tool."""

    name: str
    description: str
    handler: ToolHandler


@dataclass(frozen=True, slots=True)
class McpResource:
    """Agent-owned information exposed as an MCP resource."""

    uri: str
    name: str
    reader: ResourceReader


@dataclass(frozen=True, slots=True)
class McpPrompt:
    """An agent workflow exposed as an MCP prompt."""

    name: str
    description: str
    render: PromptRenderer


@dataclass(frozen=True, slots=True)
class AgentMcpBinding:
    """Approved MCP capabilities imported from one workspace agent."""

    agent_id: str
    tools: tuple[McpTool, ...] = ()
    resources: tuple[McpResource, ...] = ()
    prompts: tuple[McpPrompt, ...] = ()


class AgentMcpCatalog:
    """Validate and index bindings for an MCP server composition root."""

    def __init__(self, bindings: tuple[AgentMcpBinding, ...]) -> None:
        """Create a catalog and reject duplicate MCP identifiers."""
        tools = self._index(
            "tool",
            ((item.name, item) for binding in bindings for item in binding.tools),
        )
        resources = self._index(
            "resource",
            ((item.uri, item) for binding in bindings for item in binding.resources),
        )
        prompts = self._index(
            "prompt",
            ((item.name, item) for binding in bindings for item in binding.prompts),
        )
        self._tools = MappingProxyType(tools)
        self._resources = MappingProxyType(resources)
        self._prompts = MappingProxyType(prompts)

    @staticmethod
    def _index(kind: str, items: Iterable[tuple[str, Any]]) -> dict[str, Any]:
        index: dict[str, Any] = {}
        for key, item in items:
            if key in index:
                msg = f"Duplicate MCP {kind} identifier: {key}"
                raise ValueError(msg)
            index[key] = item
        return index

    @property
    def tools(self) -> Mapping[str, McpTool]:
        """Return tools indexed by MCP name."""
        return self._tools

    @property
    def resources(self) -> Mapping[str, McpResource]:
        """Return resources indexed by URI."""
        return self._resources

    @property
    def prompts(self) -> Mapping[str, McpPrompt]:
        """Return prompts indexed by MCP name."""
        return self._prompts


def bind_workspace_agent(agent: WorkspaceAgent) -> AgentMcpBinding:
    """Expose one imported workspace agent through standard MCP primitives."""
    definition = agent.definition
    mcp_name = definition.name.replace("-", "_")

    async def invoke(arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        prompt = arguments.get("prompt")
        correlation_id = arguments.get("correlation_id")
        if not isinstance(prompt, str) or not prompt.strip():
            msg = "MCP agent tool requires a non-empty string 'prompt'"
            raise ValueError(msg)
        if not isinstance(correlation_id, str) or not correlation_id.strip():
            msg = "MCP agent tool requires a non-empty string 'correlation_id'"
            raise ValueError(msg)
        async with traced_operation(
            f"mcp.run_{mcp_name}",
            attributes={
                "q2.mcp.tool.name": f"run_{mcp_name}",
                "q2.agent.name": definition.name,
                "q2.agent.correlation_id": correlation_id,
            },
            context=extracted_trace_context(arguments),
        ):
            result = await agent.run(
                AgentRequest(prompt=prompt, correlation_id=correlation_id)
            )
            warning = insufficient_benchmark_warning(definition.name)
            return {
                "output": prepend_benchmark_warning(result.output, warning),
                "correlation_id": result.correlation_id,
                "tool_calls": result.tool_calls,
                "benchmark_case_count": benchmark_case_count(definition.name),
                "warnings": (warning,) if warning is not None else (),
                "trace": current_trace_metadata(),
            }

    async def read_definition() -> str:
        return definition.description

    def render_prompt(values: Mapping[str, str]) -> str:
        request = values.get("request", "")
        return f"{definition.instructions}\n\nRequest: {request}"

    return AgentMcpBinding(
        agent_id=definition.name,
        tools=(
            McpTool(
                name=f"run_{mcp_name}",
                description=definition.description,
                handler=invoke,
            ),
        ),
        resources=(
            McpResource(
                uri=f"agent://{definition.name}/definition",
                name=f"{definition.name} definition",
                reader=read_definition,
            ),
        ),
        prompts=(
            McpPrompt(
                name=f"{mcp_name}_request",
                description=f"Prepare a request for {definition.name}.",
                render=render_prompt,
            ),
        ),
    )
