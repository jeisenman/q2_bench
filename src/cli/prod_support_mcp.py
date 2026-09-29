"""Launch the production-support MCP server with host credentials."""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable
from pathlib import Path
from typing import cast

MIN_QUOTED_VALUE_LENGTH = 2


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
    server_module = importlib.import_module("mcp_servers.prod_support")
    run_server = cast("Callable[[], None]", server_module.main)
    run_server()
