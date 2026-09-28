import pytest

from workspaces.data_engineering.agents.production_support import (
    ProductionSupportAgentConfiguration,
    PromptRegistry,
    build_agent_definition,
    default_prompt_registry,
)
from workspaces.data_engineering.agents.production_support.prompts import (
    production_benchmark_judge_prompt,
)


def test_build_agent_definition_uses_documented_prompt() -> None:
    prompts = default_prompt_registry()
    configuration = ProductionSupportAgentConfiguration(
        name="Orchestrator",
        description="Coordinate one production operation.",
        prompt_name="orchestrator",
        model="test-model",
    )

    definition = build_agent_definition(configuration, prompts)

    assert definition.name == "Orchestrator"
    assert definition.model == "test-model"
    assert definition.instructions.startswith(
        "You are a helpful production operations agent."
    )
    assert "ClusterAgent" in definition.instructions
    assert "TriageManager" in definition.instructions
    assert (
        "Present only data_internal_message as Slack-friendly mrkdwn"
        in definition.instructions
    )
    assert "follow_up_message verbatim as plain text" in definition.instructions
    assert "Use no code fences" in definition.instructions


def test_custom_prompt_keeps_process_configuration_flexible() -> None:
    def focused_prompt() -> str:
        """Inspect only the supplied scheduler evidence."""
        return "Inspect only the supplied scheduler evidence."

    prompts = PromptRegistry({"focused": focused_prompt})
    configuration = ProductionSupportAgentConfiguration(
        name="focused-agent",
        description="Inspect scheduler evidence.",
        prompt_name="focused",
    )

    definition = build_agent_definition(configuration, prompts)

    assert definition.instructions == "Inspect only the supplied scheduler evidence."


def test_prompt_registry_rejects_undocumented_prompt() -> None:
    def undocumented_prompt() -> str:
        return "hidden prompt"

    with pytest.raises(ValueError, match="must define a docstring"):
        PromptRegistry({"undocumented": undocumented_prompt})


def test_prompt_registry_reports_available_prompts() -> None:
    prompts = default_prompt_registry()

    with pytest.raises(
        KeyError,
        match=(
            "available prompts: bench_builder_agent, cluster_agent, "
            "follow_up_agent, orchestrator, production_benchmark_judge, "
            "reporter, triage_manager"
        ),
    ):
        prompts.render("missing")


def test_prompt_registry_validates_registry_boundaries() -> None:
    def documented_prompt() -> str:
        """Documented prompt."""
        return "Documented prompt."

    assert "benchmark judge" in production_benchmark_judge_prompt()
    with pytest.raises(ValueError, match="prompts must not be empty"):
        PromptRegistry({})
    with pytest.raises(ValueError, match="prompt names must not be empty"):
        PromptRegistry({" ": documented_prompt})


@pytest.mark.parametrize("field", ["name", "description", "prompt_name", "version"])
def test_configuration_rejects_empty_required_fields(field: str) -> None:
    values = {
        "name": "agent",
        "description": "description",
        "prompt_name": "orchestrator",
        "version": "1",
    }
    values[field] = " "

    with pytest.raises(ValueError, match=f"{field} must not be empty"):
        ProductionSupportAgentConfiguration(**values)
