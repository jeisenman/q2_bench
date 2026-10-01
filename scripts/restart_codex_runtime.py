"""Rebuild and restart the local MCP container without stopping Codex."""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = PROJECT_ROOT / "compose.yaml"
MCP_SERVICE = "prod-support-mcp"
MLFLOW_SERVICE = "mlflow"


class ProductionConfigurationError(RuntimeError):
    """Raised when the MCP container is not configured for production mode."""

    def __init__(self, source: object) -> None:
        """Describe the invalid configured source."""
        super().__init__(
            f"{COMPOSE_PATH} must set PROD_SUPPORT_SOURCE=production; got {source!r}"
        )


def compose_configuration() -> dict[str, Any]:
    """Load the repository Compose configuration."""
    configuration = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    if not isinstance(configuration, dict):
        raise ProductionConfigurationError(None)
    return configuration


def validate_production_configuration() -> None:
    """Require the MCP container to select live production mode."""
    configuration = compose_configuration()
    services = configuration.get("services")
    service = services.get(MCP_SERVICE) if isinstance(services, dict) else None
    environment = service.get("environment") if isinstance(service, dict) else None
    source = (
        environment.get("PROD_SUPPORT_SOURCE")
        if isinstance(environment, dict)
        else None
    )
    if source != "production":
        raise ProductionConfigurationError(source)


def restart_command(*, include_mlflow: bool) -> list[str]:
    """Build the isolated Compose command used for a full MCP refresh."""
    services = [MCP_SERVICE]
    if include_mlflow:
        services.append(MLFLOW_SERVICE)
    return [
        "docker",
        "compose",
        "up",
        "--detach",
        "--build",
        "--force-recreate",
        "--wait",
        "--wait-timeout",
        "120",
        *services,
    ]


def restart_runtime(*, include_mlflow: bool, dry_run: bool) -> None:
    """Restart MCP services without terminating Codex or its app-server."""
    validate_production_configuration()
    command = restart_command(include_mlflow=include_mlflow)
    if dry_run:
        sys.stdout.write(f"would run: {shlex.join(command)}\n")
        return
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def main() -> int:
    """Parse options and restart the configured local runtime."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--with-mlflow",
        action="store_true",
        help="Also rebuild and restart the local MLflow container.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the exact restart command without changing containers.",
    )
    args = parser.parse_args()
    restart_runtime(include_mlflow=args.with_mlflow, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
