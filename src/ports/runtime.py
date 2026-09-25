"""Agent runtime port."""

from typing import Protocol

from domain import AgentDefinition, AgentRequest, AgentResult


class AgentRuntime(Protocol):
    """Execute framework-neutral agent definitions."""

    async def run(
        self,
        definition: AgentDefinition,
        request: AgentRequest,
    ) -> AgentResult:
        """Run an agent request."""
        ...
