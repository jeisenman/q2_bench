"""Instructional agent that explains prod-support prompt evolution."""

from domain import AgentDefinition, AgentRequest, AgentResult
from observability import traced_agent_run
from workspaces.data_engineering.agents.prod_support_evolution.catalog import (
    prompt_versions,
)
from workspaces.data_engineering.agents.prod_support_evolution.reporting import (
    render_evolution,
)

PROD_SUPPORT_EVOLUTION_DEFINITION = AgentDefinition(
    name="prod-support-evolution",
    description="Teach how the prod-support prompt improved through evidence.",
    instructions=(
        "Present prompt revisions chronologically. For each revision, connect an "
        "observed weakness to the narrow rule, tool, or benchmark that addressed "
        "it. Preserve provenance and never present working-tree state as committed."
    ),
    version="1",
)


class ProdSupportEvolutionAgent:
    """Explain historical prompt changes and reusable prompting lessons."""

    @property
    def definition(self) -> AgentDefinition:
        """Return the framework-neutral agent definition."""
        return PROD_SUPPORT_EVOLUTION_DEFINITION

    @traced_agent_run
    async def run(self, request: AgentRequest) -> AgentResult:
        """Return the complete instructional evolution report."""
        versions = prompt_versions()
        return AgentResult(
            output=render_evolution(versions),
            correlation_id=request.correlation_id,
            attributes=(
                ("version_count", len(versions)),
                ("first_commit", versions[0].short_commit),
                ("latest_state", versions[-1].commit),
            ),
        )
