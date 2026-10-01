from __future__ import annotations

from typing import Any

import pytest

from mcp_servers import prod_support


@pytest.fixture
def server_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Replace startup side effects and capture MCP server arguments."""
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(prod_support, "configure_telemetry", lambda **_: None)
    monkeypatch.setattr(
        prod_support.JsonProdSupportOmissionStore,
        "ensure",
        lambda _self: None,
    )
    monkeypatch.setattr(
        prod_support.server,
        "run",
        lambda **kwargs: calls.append(kwargs),
    )
    return calls


def test_main_runs_stdio_by_default(server_calls: list[dict[str, Any]]) -> None:
    prod_support.main()

    assert server_calls == [{"transport": "stdio"}]


def test_main_runs_stateless_streamable_http(
    server_calls: list[dict[str, Any]],
) -> None:
    prod_support.main(
        transport="streamable-http",
        host="0.0.0.0",
        port=8765,
    )

    assert server_calls == [
        {
            "transport": "streamable-http",
            "host": "0.0.0.0",
            "port": 8765,
            "stateless_http": True,
        }
    ]
