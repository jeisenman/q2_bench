import pytest

from domain import (
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


def test_agent_definition_rejects_empty_model() -> None:
    with pytest.raises(ValueError, match="model must not be empty"):
        AgentDefinition(
            name="agent",
            description="Description.",
            instructions="Instructions.",
            model=" ",
        )


def test_agent_definition_rejects_empty_output_template() -> None:
    with pytest.raises(ValueError, match="output_template must not be empty"):
        AgentDefinition(
            name="agent",
            description="Description.",
            instructions="Instructions.",
            output_template=" ",
        )


def test_agent_definition_disables_delegation_by_default() -> None:
    definition = AgentDefinition(
        name="agent",
        description="Description.",
        instructions="Instructions.",
    )

    assert definition.can_delegate is False
