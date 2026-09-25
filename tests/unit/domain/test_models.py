import pytest

from agentsdk.domain import (
    AgentDefinition,
    AgentRequest,
    BenchmarkIdentity,
    ToolDefinition,
)


def test_benchmark_identity_has_qualified_name() -> None:
    identity = BenchmarkIdentity(group="data_transformation", name="prod-support")

    assert identity.qualified_name == "data_transformation/prod-support"


@pytest.mark.parametrize("value", ["", "   "])
def test_agent_request_rejects_empty_prompt(value: str) -> None:
    with pytest.raises(ValueError, match="prompt must not be empty"):
        AgentRequest(prompt=value, correlation_id="correlation")


def test_agent_definition_rejects_duplicate_tools() -> None:
    tool = ToolDefinition(name="lookup", description="Look up data.")

    with pytest.raises(ValueError, match="duplicate tool names"):
        AgentDefinition(
            name="agent",
            description="Description.",
            instructions="Instructions.",
            tools=(tool, tool),
        )
