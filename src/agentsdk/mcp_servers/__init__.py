"""MCP composition interfaces for workspace agents."""

from agentsdk.mcp_servers.composition import (
    AgentMcpBinding,
    AgentMcpCatalog,
    McpPrompt,
    McpResource,
    McpTool,
    bind_workspace_agent,
)

__all__ = [
    "AgentMcpBinding",
    "AgentMcpCatalog",
    "McpPrompt",
    "McpResource",
    "McpTool",
    "bind_workspace_agent",
]
