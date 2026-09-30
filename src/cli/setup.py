"""Interactive setup for per-user workspace configuration."""

from __future__ import annotations

from pathlib import Path

import click

from adapters.local.configuration import (
    DEFAULT_CONFIGURATION_PATH,
    DEFAULT_CONFIGURATION_TEMPLATE,
    DEFAULT_DATA_ENGINEERING_REPOSITORIES_ROOT,
    UserConfigurationError,
    configure_data_engineering_repositories,
)


@click.command("setup")
@click.option(
    "--repositories-root",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_DATA_ENGINEERING_REPOSITORIES_ROOT,
    show_default="~/ra",
    prompt="Data Engineering repositories directory",
    help="Parent directory containing local Data Engineering repositories.",
)
@click.option(
    "--configuration",
    "configuration_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DEFAULT_CONFIGURATION_PATH,
    show_default=True,
)
@click.option(
    "--template",
    "template_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DEFAULT_CONFIGURATION_TEMPLATE,
    show_default=True,
)
def setup(
    repositories_root: Path,
    configuration_path: Path,
    template_path: Path,
) -> None:
    """Configure the local directory that contains DE repositories."""
    try:
        configured_root = configure_data_engineering_repositories(
            repositories_root,
            path=configuration_path,
            template_path=template_path,
        )
    except UserConfigurationError as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"configuration\t{configuration_path}")
    click.echo(f"data-engineering-repositories\t{configured_root}")
