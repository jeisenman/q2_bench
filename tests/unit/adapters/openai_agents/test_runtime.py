import asyncio
from types import SimpleNamespace
from typing import ClassVar

import pytest

from adapters.openai_agents import runtime
from domain import AgentDefinition, AgentRequest, ToolDefinition


class FakeAgent:
    received: ClassVar[dict[str, object]] = {}

    def __init__(self, **kwargs: object) -> None:
        self.received = kwargs
        FakeAgent.received = kwargs


class FakeRunner:
    @staticmethod
    async def run(agent: FakeAgent, prompt: str) -> SimpleNamespace:
        assert agent.received["model"] == "openai.gpt-5.6-luna"
        return SimpleNamespace(final_output=f"  report for {prompt}  ")


def test_runtime_executes_declared_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime, "Agent", FakeAgent)
    monkeypatch.setattr(runtime, "Runner", FakeRunner)
    definition = AgentDefinition(
        name="reporter",
        description="Write a report.",
        instructions="Use only supplied evidence.",
        model="openai.gpt-5.6-luna",
        output_template="Message for developer:\n  - <finding>",
    )

    result = asyncio.run(
        runtime.OpenAIAgentsRuntime().run(
            definition,
            AgentRequest(prompt="findings", correlation_id="case-1"),
        )
    )

    assert result.output == "report for findings"
    assert result.correlation_id == "case-1"
    assert dict(result.attributes)["model"] == "openai.gpt-5.6-luna"
    assert FakeAgent.received["handoff_description"] == "Write a report."
    instructions = str(FakeAgent.received["instructions"])
    assert "Delegation is disabled" in instructions
    assert "Replace angle-bracket placeholders" in instructions
    assert "Message for developer:" in instructions


@pytest.mark.parametrize(
    "definition",
    [
        AgentDefinition("missing-model", "Description.", "Instructions."),
        AgentDefinition(
            "tool-agent",
            "Description.",
            "Instructions.",
            tools=(ToolDefinition("lookup", "Look up evidence."),),
            model="openai.gpt-5.6-luna",
        ),
        AgentDefinition(
            "orchestrator",
            "Description.",
            "Instructions.",
            model="openai.gpt-5.6-luna",
            can_delegate=True,
        ),
    ],
)
def test_runtime_rejects_unsupported_definitions(
    definition: AgentDefinition,
) -> None:
    with pytest.raises(runtime.OpenAIAgentsRuntimeError):
        asyncio.run(
            runtime.OpenAIAgentsRuntime().run(
                definition,
                AgentRequest(prompt="findings", correlation_id="case-1"),
            )
        )
