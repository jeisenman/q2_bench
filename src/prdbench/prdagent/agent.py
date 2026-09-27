"""Build production benchmark agents from explicit prompt definitions."""

from __future__ import annotations

from dataclasses import dataclass

from domain import AgentDefinition, ToolDefinition
from prdbench.prdagent.prompts import PromptRegistry


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        message = f"{field_name} must not be empty"
        raise ValueError(message)


@dataclass(frozen=True, slots=True)
class PrdAgentConfiguration:
    """Describe one configurable production benchmark agent."""

    name: str
    description: str
    prompt_name: str
    tools: tuple[ToolDefinition, ...] = ()
    model: str | None = None
    version: str = "1"

    def __post_init__(self) -> None:
        """Validate required configuration at the package boundary."""
        _require_text(self.name, "name")
        _require_text(self.description, "description")
        _require_text(self.prompt_name, "prompt_name")
        _require_text(self.version, "version")
        if self.model is not None:
            _require_text(self.model, "model")


def build_agent_definition(
    configuration: PrdAgentConfiguration,
    prompts: PromptRegistry,
) -> AgentDefinition:
    """Build an agent definition using a named, documented prompt."""
    return AgentDefinition(
        name=configuration.name,
        description=configuration.description,
        instructions=prompts.render(configuration.prompt_name),
        tools=configuration.tools,
        version=configuration.version,
        model=configuration.model,
    )
