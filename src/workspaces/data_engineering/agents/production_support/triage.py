"""Deterministic placeholder for production failure triage."""

from domain import AgentDefinition, AgentRequest, AgentResult
from observability import traced_agent_run
from workspaces.data_engineering.agents.production_support.prompts import (
    triage_agent_prompt,
)

TRIAGE_NOT_SETUP = "Triage agent hasn't been setup."
TRIAGE_AGENT_DEFINITION = AgentDefinition(
    name="TriageAgent",
    description="Return the current triage implementation status.",
    instructions=triage_agent_prompt(),
)


class TriageAgent:
    """Return a deterministic placeholder until triage is implemented."""

    definition = TRIAGE_AGENT_DEFINITION

    @traced_agent_run
    async def run(self, request: AgentRequest) -> AgentResult:
        """Return the unimplemented status without invoking tools."""
        return AgentResult(
            output=TRIAGE_NOT_SETUP,
            correlation_id=request.correlation_id,
        )
