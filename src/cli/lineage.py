"""CLI entry point for repository lineage synchronization."""

from __future__ import annotations

from pathlib import Path

import click

from adapters.postgres.lineage import PostgresLineageStore
from workspaces.data_engineering.workflows.lineage.radar_repositories import (
    RadarRepositories,
)
from workspaces.data_engineering.workflows.lineage.workflow import (
    sync_radar_lineage,
)

DEFAULT_DI_PIPELINES_REPOSITORY = Path("../di-pipelines")
DEFAULT_RADAR_NOTEBOOKS_REPOSITORY = Path("../radar-notebooks")
DEFAULT_RADAR_LIBRARIES_REPOSITORY = Path("../radar-libraries")
DEFAULT_RADAR_ADF_REPOSITORY = Path("../radar-adf-pipeline")
DEFAULT_DATA_INGRESS_REPOSITORY = Path("../pl-dataingress")
DEFAULT_ENGINE_REPOSITORY = Path("../pl-calculation-engine")


@click.command("lineage-sync")
@click.option(
    "--repository",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_DI_PIPELINES_REPOSITORY,
    show_default=True,
    help="DI Pipelines repository.",
)
@click.option(
    "--radar-notebooks-repository",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_RADAR_NOTEBOOKS_REPOSITORY,
    show_default=True,
)
@click.option(
    "--radar-libraries-repository",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_RADAR_LIBRARIES_REPOSITORY,
    show_default=True,
)
@click.option(
    "--radar-adf-repository",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_RADAR_ADF_REPOSITORY,
    show_default=True,
)
@click.option(
    "--data-ingress-repository",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_DATA_INGRESS_REPOSITORY,
    show_default=True,
)
@click.option(
    "--engine-repository",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_ENGINE_REPOSITORY,
    show_default=True,
)
@click.option(
    "--source-ref",
    default=None,
    help="Aggregate source label recorded in the graph manifest.",
)
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Optional JSON artifact path.",
)
@click.option(
    "--dsn",
    envvar="LINEAGE_POSTGRES_DSN",
    help="PostgreSQL DSN; required unless --dry-run is used.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Build and diff without writing to PostgreSQL.",
)
def sync_lineage(**options: object) -> None:
    """Extract aggregate RADAR lineage and persist one immutable version."""
    repositories = RadarRepositories(
        di_pipelines=_path_option(options, "repository"),
        radar_notebooks=_path_option(options, "radar_notebooks_repository"),
        radar_libraries=_path_option(options, "radar_libraries_repository"),
        radar_adf=_path_option(options, "radar_adf_repository"),
        data_ingress=_path_option(options, "data_ingress_repository"),
        calculation_engine=_path_option(options, "engine_repository"),
    )
    for name, repository in repositories.as_mapping().items():
        if repository.is_dir():
            continue
        message = f"{name} repository does not exist: {repository}"
        raise click.ClickException(message)
    dry_run = bool(options["dry_run"])
    dsn = _optional_string(options.get("dsn"))
    if not dry_run and not dsn:
        message = "LINEAGE_POSTGRES_DSN or --dsn is required unless --dry-run is used"
        raise click.ClickException(message)
    store = PostgresLineageStore(dsn) if dsn and not dry_run else None
    outcome = sync_radar_lineage(
        repositories,
        store,
        source_ref=_optional_string(options.get("source_ref")),
    )
    output = _optional_path(options.get("output"))
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(outcome.graph.to_json(), encoding="utf-8")
    status = "inserted" if outcome.inserted else "not-persisted"
    if store is not None and not outcome.inserted:
        status = "already-stored"
    click.echo(
        "\t".join(
            (
                outcome.graph.manifest.repository,
                outcome.graph.manifest.commit_sha,
                f"nodes={len(outcome.graph.nodes)}",
                f"edges={len(outcome.graph.edges)}",
                f"changed={str(outcome.diff.changed).lower()}",
                status,
            )
        )
    )


def _path_option(options: dict[str, object], name: str) -> Path:
    value = options[name]
    if not isinstance(value, Path):
        message = f"invalid path option: {name}"
        raise click.ClickException(message)
    return value


def _optional_path(value: object) -> Path | None:
    if value is None or isinstance(value, Path):
        return value
    message = "invalid output path"
    raise click.ClickException(message)


def _optional_string(value: object) -> str | None:
    if value is None or isinstance(value, str):
        return value
    message = "invalid string option"
    raise click.ClickException(message)
