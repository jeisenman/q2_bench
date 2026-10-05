"""CLI entry point for repository lineage synchronization."""

from __future__ import annotations

from pathlib import Path

import click

from adapters.postgres.lineage import PostgresLineageStore
from workspaces.data_engineering.workflows.lineage.workflow import (
    sync_di_pipelines_lineage,
)

DEFAULT_DI_PIPELINES_REPOSITORY = Path("../di-pipelines")


@click.command("lineage-sync")
@click.option(
    "--repository",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_DI_PIPELINES_REPOSITORY,
    show_default=True,
)
@click.option(
    "--source-ref",
    default=None,
    help="Source branch or ref recorded in the graph manifest.",
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
def sync_lineage(
    repository: Path,
    source_ref: str | None,
    output: Path | None,
    dsn: str | None,
    dry_run: bool,
) -> None:
    """Extract the DI Pipelines graph and persist one immutable version."""
    if not repository.is_dir():
        message = f"DI Pipelines repository does not exist: {repository}"
        raise click.ClickException(message)
    if not dry_run and not dsn:
        message = "LINEAGE_POSTGRES_DSN or --dsn is required unless --dry-run is used"
        raise click.ClickException(message)
    store = PostgresLineageStore(dsn) if dsn and not dry_run else None
    outcome = sync_di_pipelines_lineage(
        repository,
        store,
        source_ref=source_ref,
    )
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
