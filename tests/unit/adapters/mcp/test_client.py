from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest
from mcp import types

from adapters.mcp import McpToolCallError, StdioMcpToolCaller, project_stdio_caller
from adapters.mcp import client as client_module


class FakeSession:
    result: object

    def __init__(self, read_stream: object, write_stream: object) -> None:
        del read_stream, write_stream

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        del args

    async def initialize(self) -> None:
        return None

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        assert name == "example"
        assert arguments == {"value": 1}
        return self.result


@asynccontextmanager
async def fake_stdio(parameters):
    assert parameters.command == "uv"
    yield object(), object()


def _call(monkeypatch: pytest.MonkeyPatch, result: object) -> object:
    FakeSession.result = result
    monkeypatch.setattr(client_module, "ClientSession", FakeSession)
    monkeypatch.setattr(client_module, "stdio_client", fake_stdio)
    caller = StdioMcpToolCaller("uv", ("run",), client_module.Path.cwd())
    return asyncio.run(caller.call_tool("example", {"value": 1}))


def test_stdio_mcp_caller_accepts_structured_and_text_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    structured = types.CallToolResult(
        content=[],
        structuredContent={"status": "ready"},
    )
    text = types.CallToolResult(
        content=[types.TextContent(text='{"status": "ready"}')],
    )

    assert _call(monkeypatch, structured) == {"status": "ready"}
    assert _call(monkeypatch, text) == {"status": "ready"}


@pytest.mark.parametrize(
    ("result", "message"),
    [
        (
            types.CallToolResult(
                content=[types.TextContent(text="denied")],
                isError=True,
            ),
            "failed: denied",
        ),
        (
            types.CallToolResult(content=[types.TextContent(text="{")]),
            "invalid JSON",
        ),
        (
            types.CallToolResult(content=[types.TextContent(text="[]")]),
            "structured object",
        ),
        (object(), "incomplete"),
    ],
)
def test_stdio_mcp_caller_rejects_invalid_results(
    monkeypatch: pytest.MonkeyPatch,
    result: object,
    message: str,
) -> None:
    with pytest.raises(McpToolCallError, match=message):
        _call(monkeypatch, result)


def test_project_stdio_caller_builds_project_command() -> None:
    caller = project_stdio_caller("airflow-mcp")

    assert caller.command == "uv"
    assert caller.args[-1] == "airflow-mcp"
    with pytest.raises(ValueError, match="must not be empty"):
        project_stdio_caller(" ")
