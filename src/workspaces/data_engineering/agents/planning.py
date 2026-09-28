"""Shared deterministic planning runtime for scaffolded agents."""

from __future__ import annotations

from dataclasses import dataclass

from domain import AgentDefinition, AgentRequest, AgentResult
from observability import traced_agent_run


@dataclass(frozen=True, slots=True)
class WorkflowStep:
    """Describe one ordered, externally visible workflow step."""

    name: str
    outcome: str

    def __post_init__(self) -> None:
        """Reject incomplete workflow steps."""
        if not self.name.strip():
            message = "step name must not be empty"
            raise ValueError(message)
        if not self.outcome.strip():
            message = "step outcome must not be empty"
            raise ValueError(message)


class DeterministicPlanningAgent:
    """Render a stable execution plan without invoking external systems."""

    def __init__(
        self,
        definition: AgentDefinition,
        steps: tuple[WorkflowStep, ...],
    ) -> None:
        """Create an agent from immutable metadata and workflow steps."""
        if not steps:
            message = "steps must not be empty"
            raise ValueError(message)
        self._definition = definition
        self._steps = steps

    @property
    def definition(self) -> AgentDefinition:
        """Return the immutable agent definition."""
        return self._definition

    @traced_agent_run
    async def run(self, request: AgentRequest) -> AgentResult:
        """Return the deterministic plan for an already validated request."""
        rendered_steps = "\n".join(
            f"{index}. {step.name}: {step.outcome}"
            for index, step in enumerate(self._steps, start=1)
        )
        return AgentResult(
            output=f"Objective: {request.prompt}\nPlan:\n{rendered_steps}",
            correlation_id=request.correlation_id,
            tool_calls=tuple(tool.name for tool in self._definition.tools),
            attributes=(
                ("agent_version", self._definition.version),
                ("execution_mode", "plan_only"),
                ("step_count", len(self._steps)),
            ),
        )
