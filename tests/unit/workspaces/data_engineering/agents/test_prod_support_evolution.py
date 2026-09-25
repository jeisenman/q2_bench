import asyncio

from domain import AgentRequest
from workspaces.data_engineering.agents.prod_support_evolution import (
    ProdSupportEvolutionAgent,
    prompt_versions,
)


def test_prompt_versions_are_chronological_and_provenanced() -> None:
    versions = prompt_versions()

    assert tuple(version.version for version in versions) == ("v0", "v1", "v2", "v3")
    assert versions[0].short_commit == "c11a9a7e"
    assert versions[-1].commit == "working-tree-2026-09-25"


def test_evolution_agent_connects_weaknesses_to_improvements() -> None:
    result = asyncio.run(
        ProdSupportEvolutionAgent().run(
            AgentRequest(
                prompt="Teach me how the prompt evolved.",
                correlation_id="history-1",
            )
        )
    )

    assert "# Prod-support prompt evolution" in result.output
    assert "Weakness:" in result.output
    assert "Improvement:" in result.output
    assert ("version_count", 4) in result.attributes
