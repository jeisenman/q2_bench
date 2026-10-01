from __future__ import annotations

import os
from pathlib import Path

import pytest

from cli.prod_support_mcp import (
    McpRuntimeConfiguration,
    McpRuntimeConfigurationError,
    configure_environment,
    runtime_configuration,
)


def test_configure_environment_loads_dotenv_and_defaults_to_production(
    monkeypatch,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "USAIRFLORUSER='us-user'\nCAAIRFLOWPASSWORD=ca-password\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("USAIRFLORUSER", raising=False)
    monkeypatch.delenv("CAAIRFLOWPASSWORD", raising=False)
    monkeypatch.delenv("PROD_SUPPORT_SOURCE", raising=False)

    configure_environment(env_file)

    assert os.environ["USAIRFLORUSER"] == "us-user"
    assert os.environ["CAAIRFLOWPASSWORD"] == "ca-password"
    assert os.environ["PROD_SUPPORT_SOURCE"] == "production"


def test_configure_environment_preserves_explicit_mode_and_credentials(
    monkeypatch,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "USAIRFLORUSER=file-user\nPROD_SUPPORT_SOURCE=production\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("USAIRFLORUSER", "shell-user")
    monkeypatch.setenv("PROD_SUPPORT_SOURCE", "replay")

    configure_environment(env_file)

    assert os.environ["USAIRFLORUSER"] == "shell-user"
    assert os.environ["PROD_SUPPORT_SOURCE"] == "replay"


def test_runtime_configuration_defaults_to_stdio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PROD_SUPPORT_MCP_TRANSPORT", raising=False)

    assert runtime_configuration() == McpRuntimeConfiguration(transport="stdio")


def test_runtime_configuration_loads_streamable_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROD_SUPPORT_MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("PROD_SUPPORT_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("PROD_SUPPORT_MCP_PORT", "8765")

    assert runtime_configuration() == McpRuntimeConfiguration(
        transport="streamable-http",
        host="0.0.0.0",
        port=8765,
    )


@pytest.mark.parametrize("port", ["zero", "0", "65536"])
def test_runtime_configuration_rejects_invalid_http_port(
    monkeypatch: pytest.MonkeyPatch,
    port: str,
) -> None:
    monkeypatch.setenv("PROD_SUPPORT_MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("PROD_SUPPORT_MCP_PORT", port)

    with pytest.raises(
        McpRuntimeConfigurationError,
        match="PROD_SUPPORT_MCP_PORT",
    ):
        runtime_configuration()
