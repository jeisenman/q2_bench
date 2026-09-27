import asyncio

from domain import AgentRequest
from workspaces.data_engineering.agents.production_support import (
    TRIAGE_NOT_SETUP,
    TriageAgent,
)


def test_triage_agent_returns_not_setup_without_tools() -> None:
    agent = TriageAgent()

    result = asyncio.run(
        agent.run(
            AgentRequest(
                prompt="Triage this failure.",
                correlation_id="triage-1",
            )
        )
    )

    assert result.output == "Triage agent hasn't been setup."
    assert result.output == TRIAGE_NOT_SETUP
    assert result.correlation_id == "triage-1"
    assert result.tool_calls == ()
    assert agent.definition.tools == ()
