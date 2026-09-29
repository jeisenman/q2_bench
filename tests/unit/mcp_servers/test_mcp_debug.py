"""Tests for local MCP lifecycle diagnostics."""

from __future__ import annotations

from mcp_servers.debug import McpDebugTrace


def test_debug_trace_is_disabled_by_default(
    monkeypatch,
) -> None:
    monkeypatch.delenv("Q2_MCP_DEBUG", raising=False)
    trace = McpDebugTrace("tool", "correlation-1")

    trace.event("tool.start", candidate_count=2)

    assert trace.enabled is False
    assert trace.result() == {}


def test_debug_trace_records_bounded_events(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("Q2_MCP_DEBUG", "1")
    trace = McpDebugTrace("tool", "correlation-1")

    trace.event("tool.start", candidate_count=2)
    result = trace.result()

    assert trace.enabled is True
    assert result["enabled"] is True
    assert result["tool"] == "tool"
    assert result["correlation_id"] == "correlation-1"
    assert result["events"][0]["event"] == "tool.start"
    assert '"candidate_count": 2' in capsys.readouterr().err
