"""Register focused production-support agent definitions as MCP resources."""

from mcp.server.mcpserver import MCPServer

from workspaces.data_engineering.agents.production_support import (
    CLASSIFICATION_AGENT_DEFINITION,
    PROD_SUPPORT_REPORTER_DEFINITION,
)


def register_prod_support_agent_resources(server: MCPServer) -> None:
    """Expose classification and reporter Markdown instructions."""

    async def classification_definition() -> str:
        """Return the Classification Agent instructions."""
        return CLASSIFICATION_AGENT_DEFINITION.instructions

    async def reporter_definition() -> str:
        """Return the Reporter Agent instructions."""
        return PROD_SUPPORT_REPORTER_DEFINITION.instructions

    server.resource(
        "agent://prod-support/classification/definition",
        name="prod-support classification definition",
        description="Exact-evidence classification and DV mapping workflow.",
    )(classification_definition)
    server.resource(
        "agent://prod-support/reporter/definition",
        name="prod-support reporter definition",
        description="Evidence-qualified production-support reporting workflow.",
    )(reporter_definition)
