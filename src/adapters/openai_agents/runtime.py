"""Execute framework-neutral definitions with the OpenAI Agents SDK."""

from __future__ import annotations

from agents import Agent, Runner

from domain import AgentDefinition, AgentRequest, AgentResult
from observability import traced_runtime_run


class OpenAIAgentsRuntimeError(RuntimeError):
    """Raised when a definition cannot be executed by this adapter."""


class OpenAIAgentsRuntime:
    """Run tool-free specialist agents through the OpenAI Agents SDK."""

    @traced_runtime_run
    async def run(
        self,
        definition: AgentDefinition,
        request: AgentRequest,
    ) -> AgentResult:
        """Execute one model-backed agent request."""
        if definition.can_delegate:
            message = (
                f"agent {definition.name!r} permits delegation, but this runtime "
                "executes leaf agents only"
            )
            raise OpenAIAgentsRuntimeError(message)
        if definition.model is None:
            message = f"agent {definition.name!r} does not declare a model"
            raise OpenAIAgentsRuntimeError(message)
        if definition.tools:
            message = (
                f"agent {definition.name!r} declares tools, but this runtime "
                "requires callable tool adapters"
            )
            raise OpenAIAgentsRuntimeError(message)
        agent = Agent(
            name=definition.name,
            handoff_description=definition.description,
            instructions=_instructions(definition),
            model=definition.model,
        )
        result = await Runner.run(agent, request.prompt)
        output = result.final_output
        if not isinstance(output, str) or not output.strip():
            message = f"agent {definition.name!r} returned no text"
            raise OpenAIAgentsRuntimeError(message)
        return AgentResult(
            output=output.strip(),
            correlation_id=request.correlation_id,
            attributes=(("model", definition.model),),
        )


def _instructions(definition: AgentDefinition) -> str:
    sections = [
        definition.instructions,
        (
            "Delegation is disabled. Complete this task directly; do not spawn, "
            "handoff to, or invoke another agent."
        ),
    ]
    if definition.output_template is not None:
        sections.extend(
            (
                (
                    "Use the output template below. Replace angle-bracket "
                    "placeholders with supplied evidence, omit inapplicable optional "
                    "lines, preserve the heading and indentation, and do not copy "
                    "placeholder text into the final output."
                ),
                definition.output_template,
            )
        )
    return "\n\n".join(sections)
