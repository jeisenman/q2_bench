"""Workspace-level executable agent contract."""

from typing import Protocol

from agentsdk.domain import AgentDefinition, AgentRequest, AgentResult


class WorkspaceAgent(Protocol):
    """Expose an agent definition and execute requests."""

    @property
    def definition(self) -> AgentDefinition:
        """Return immutable agent metadata."""
        ...

    async def run(self, request: AgentRequest) -> AgentResult:
        """Execute one request."""
        ...
