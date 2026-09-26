"""CLI commands for configuring MLflow integrations."""

from __future__ import annotations

import os
from pathlib import Path

import click

from adapters.mlflow import (
    CodexTracingConfigurationError,
    CodexTracingConfigurator,
)

DEFAULT_CODEX_HOME = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))


@click.command("configure-codex-tracing")
@click.option(
    "--tracking-uri",
    default="http://localhost:5000",
    show_default=True,
)
@click.option("--experiment-id", default="0", show_default=True)
@click.option(
    "--codex-home",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_CODEX_HOME,
    show_default=True,
)
@click.option(
    "--project-root",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path(),
    show_default=True,
)
def configure_codex_tracing(
    tracking_uri: str,
    experiment_id: str,
    codex_home: Path,
    project_root: Path,
) -> None:
    """Configure Codex CLI turns to emit conversation traces to MLflow."""
    try:
        configured = CodexTracingConfigurator(
            codex_home=codex_home,
            project_root=project_root,
        ).configure(
            tracking_uri=tracking_uri,
            experiment_id=experiment_id,
        )
    except CodexTracingConfigurationError as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"codex-config\t{configured.codex_config}")
    click.echo(f"tracing-config\t{configured.tracing_config}")
