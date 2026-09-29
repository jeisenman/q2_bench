"""Local-only MCP lifecycle diagnostics."""

from __future__ import annotations

import json
import os
import sys
import time
from typing import TypeAlias

MCP_DEBUG_ENV = "Q2_MCP_DEBUG"
_ENABLED_VALUES = frozenset({"1", "true", "yes", "on", "debug"})
DebugValue: TypeAlias = str | int | float | bool | None


def mcp_debug_enabled() -> bool:
    """Return whether local MCP diagnostics are enabled."""
    return os.environ.get(MCP_DEBUG_ENV, "").strip().lower() in _ENABLED_VALUES


class McpDebugTrace:
    """Collect bounded local MCP events and mirror them to stderr."""

    def __init__(self, tool_name: str, correlation_id: str) -> None:
        """Start one request-local debug trace."""
        self._tool_name = tool_name
        self._correlation_id = correlation_id
        self._started_at = time.monotonic()
        self._enabled = mcp_debug_enabled()
        self._events: list[dict[str, DebugValue]] = []

    @property
    def enabled(self) -> bool:
        """Return whether this trace is recording events."""
        return self._enabled

    def event(self, name: str, **fields: DebugValue) -> None:
        """Record one bounded lifecycle event when debug mode is enabled."""
        if not self._enabled:
            return
        event: dict[str, DebugValue] = {
            "tool": self._tool_name,
            "correlation_id": self._correlation_id,
            "event": name,
            "elapsed_ms": round((time.monotonic() - self._started_at) * 1000, 2),
            **fields,
        }
        self._events.append(event)
        sys.stderr.write(json.dumps(event, sort_keys=True) + "\n")
        sys.stderr.flush()

    def result(self) -> dict[str, object]:
        """Return the bounded trace payload for an MCP response."""
        if not self._enabled:
            return {}
        return {
            "enabled": True,
            "tool": self._tool_name,
            "correlation_id": self._correlation_id,
            "events": list(self._events),
        }
