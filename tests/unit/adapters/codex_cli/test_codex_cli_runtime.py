import asyncio
from pathlib import Path

import pytest

from adapters.codex_cli import runtime
from domain import AgentDefinition, AgentRequest, ToolDefinition


class FakeProcess:
    returncode = 0

    def __init__(self, command: tuple[object, ...]) -> None:
        self._command = command

    async def communicate(self, prompt: bytes) -> tuple[bytes, bytes]:
        output_flag = self._command.index("--output-last-message") + 1
        Path(str(self._command[output_flag])).write_text(" report ", encoding="utf-8")
        assert b"Input evidence:\n\nfindings" in prompt
        return b"", b""


def test_runtime_uses_codex_home_and_declared_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / "config.toml").write_text(
        'model_provider = "amazon-bedrock"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    received: list[tuple[object, ...]] = []

    async def fake_create(*command: object, **_: object) -> FakeProcess:
        received.append(command)
        return FakeProcess(command)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    definition = AgentDefinition(
        name="reporter",
        description="Write a report.",
        instructions="Use supplied evidence.",
        model="openai.gpt-5.6-luna",
    )

    result = asyncio.run(
        runtime.CodexCliRuntime().run(
            definition,
            AgentRequest(prompt="findings", correlation_id="case-1"),
        )
    )

    assert result.output == "report"
    assert result.correlation_id == "case-1"
    assert received[0][:3] == ("codex", "--model", "openai.gpt-5.6-luna")
    assert dict(result.attributes)["runtime"] == "codex-cli"


def test_runtime_rejects_invalid_codex_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "missing"))
    definition = AgentDefinition(
        "reporter",
        "Write a report.",
        "Use supplied evidence.",
        model="model",
    )

    with pytest.raises(runtime.CodexCliRuntimeError, match="initialized"):
        asyncio.run(
            runtime.CodexCliRuntime().run(
                definition,
                AgentRequest(prompt="findings", correlation_id="case-1"),
            )
        )


def test_runtime_rejects_missing_codex_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    definition = AgentDefinition(
        "reporter",
        "Write a report.",
        "Use supplied evidence.",
        model="model",
    )

    with pytest.raises(runtime.CodexCliRuntimeError, match="configuration is missing"):
        asyncio.run(
            runtime.CodexCliRuntime().run(
                definition,
                AgentRequest(prompt="findings", correlation_id="case-1"),
            )
        )


@pytest.mark.parametrize(
    "definition",
    [
        AgentDefinition("missing", "Description.", "Instructions."),
        AgentDefinition(
            "tools",
            "Description.",
            "Instructions.",
            tools=(ToolDefinition("lookup", "Look up evidence."),),
            model="model",
        ),
        AgentDefinition(
            "delegate",
            "Description.",
            "Instructions.",
            model="model",
            can_delegate=True,
        ),
    ],
)
def test_runtime_rejects_unsupported_definitions(
    definition: AgentDefinition,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))

    with pytest.raises(runtime.CodexCliRuntimeError):
        asyncio.run(
            runtime.CodexCliRuntime().run(
                definition,
                AgentRequest(prompt="findings", correlation_id="case-1"),
            )
        )
