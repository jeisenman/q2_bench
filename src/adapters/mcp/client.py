"""Typed stdio MCP client boundary for capability adapters."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client


class McpToolCallError(RuntimeError):
    """Raised when an MCP capability returns an invalid or failed response."""

    @classmethod
    def incomplete(cls, name: str) -> McpToolCallError:
        """Return an error for a non-terminal tool response."""
        return cls(f"MCP tool {name!r} returned an incomplete result")

    @classmethod
    def failed(cls, name: str, detail: str) -> McpToolCallError:
        """Return an error reported by the remote tool."""
        return cls(f"MCP tool {name!r} failed: {detail}")

    @classmethod
    def invalid_json(cls, name: str) -> McpToolCallError:
        """Return an error for invalid fallback JSON text."""
        return cls(f"MCP tool {name!r} returned invalid JSON text")

    @classmethod
    def object_required(cls, name: str) -> McpToolCallError:
        """Return an error for a non-object structured result."""
        return cls(f"MCP tool {name!r} must return a structured object")


class McpToolCaller(Protocol):
    """Call one named MCP tool and return its structured object result."""

    async def call_tool(
        self,
        name: str,
        arguments: Mapping[str, object],
    ) -> Mapping[str, object]:
        """Call one tool with JSON-compatible arguments."""
        ...


@dataclass(frozen=True, slots=True)
class StdioMcpToolCaller:
    """Call a dedicated MCP server process over stdio."""

    command: str
    args: tuple[str, ...]
    cwd: Path
    environment: tuple[tuple[str, str], ...] = ()

    async def call_tool(
        self,
        name: str,
        arguments: Mapping[str, object],
    ) -> Mapping[str, object]:
        """Start the server, call one tool, and validate its object result."""
        parameters = StdioServerParameters(
            command=self.command,
            args=list(self.args),
            cwd=self.cwd,
            env={**os.environ, **dict(self.environment)},
        )
        async with (
            stdio_client(parameters) as (read_stream, write_stream),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            result = await session.call_tool(name, dict(arguments))
        if not isinstance(result, types.CallToolResult):
            raise McpToolCallError.incomplete(name)
        if result.is_error:
            detail = _text_content(result.content) or "unspecified MCP tool error"
            raise McpToolCallError.failed(name, detail)
        payload = result.structured_content
        if isinstance(payload, Mapping):
            return payload
        text = _text_content(result.content)
        if text:
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError as error:
                raise McpToolCallError.invalid_json(name) from error
            if isinstance(decoded, Mapping):
                return decoded
        raise McpToolCallError.object_required(name)


def project_stdio_caller(entrypoint: str) -> StdioMcpToolCaller:
    """Return the standard local stdio command for one project MCP server."""
    if not entrypoint.strip():
        message = "MCP entrypoint must not be empty"
        raise ValueError(message)
    project_root = Path(__file__).resolve().parents[3]
    return StdioMcpToolCaller(
        command="uv",
        args=("run", "--directory", str(project_root), entrypoint),
        cwd=project_root,
    )


def _text_content(content: list[types.ContentBlock]) -> str:
    return "\n".join(
        item.text for item in content if isinstance(item, types.TextContent)
    ).strip()
