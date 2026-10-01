"""Launch the production-support MCP server with host credentials."""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

MIN_QUOTED_VALUE_LENGTH = 2
DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8000
MAX_PORT = 65_535
Transport = Literal["stdio", "streamable-http"]


@dataclass(frozen=True)
class McpRuntimeConfiguration:
    """Runtime transport configuration for the production-support MCP."""

    transport: Transport
    host: str = DEFAULT_HTTP_HOST
    port: int = DEFAULT_HTTP_PORT


class McpRuntimeConfigurationError(ValueError):
    """Raised when MCP runtime environment variables are invalid."""

    @classmethod
    def empty_host(cls) -> McpRuntimeConfigurationError:
        """Create an error for an empty HTTP bind host."""
        return cls("PROD_SUPPORT_MCP_HOST must not be empty")


def runtime_configuration() -> McpRuntimeConfiguration:
    """Load and validate MCP transport settings from the environment."""
    raw_transport = os.environ.get("PROD_SUPPORT_MCP_TRANSPORT", "stdio").strip()
    if raw_transport not in {"stdio", "streamable-http"}:
        msg = (
            "PROD_SUPPORT_MCP_TRANSPORT must be 'stdio' or "
            f"'streamable-http'; got {raw_transport!r}"
        )
        raise McpRuntimeConfigurationError(msg)
    transport = cast("Transport", raw_transport)
    if transport == "stdio":
        return McpRuntimeConfiguration(transport=transport)

    host = os.environ.get("PROD_SUPPORT_MCP_HOST", DEFAULT_HTTP_HOST).strip()
    if not host:
        raise McpRuntimeConfigurationError.empty_host()
    raw_port = os.environ.get(
        "PROD_SUPPORT_MCP_PORT",
        str(DEFAULT_HTTP_PORT),
    ).strip()
    try:
        port = int(raw_port)
    except ValueError as exc:
        msg = f"PROD_SUPPORT_MCP_PORT must be an integer; got {raw_port!r}"
        raise McpRuntimeConfigurationError(msg) from exc
    if not 1 <= port <= MAX_PORT:
        msg = f"PROD_SUPPORT_MCP_PORT must be between 1 and 65535; got {port}"
        raise McpRuntimeConfigurationError(msg)
    return McpRuntimeConfiguration(transport=transport, host=host, port=port)


def configure_environment(env_file: Path = Path(".env")) -> None:
    """Load local credentials and default the server to live production mode."""
    if env_file.is_file():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            value = value.strip()
            if (
                len(value) >= MIN_QUOTED_VALUE_LENGTH
                and value[0] == value[-1]
                and value[0] in {"'", '"'}
            ):
                value = value[1:-1]
            os.environ[key] = value
    os.environ.setdefault("PROD_SUPPORT_SOURCE", "production")


def main() -> None:
    """Start the production-support MCP server."""
    configure_environment()
    runtime = runtime_configuration()
    server_module = importlib.import_module("mcp_servers.prod_support")
    run_server = cast("Callable[..., None]", server_module.main)
    run_server(
        transport=runtime.transport,
        host=runtime.host,
        port=runtime.port,
    )
