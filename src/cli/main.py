"""Local application commands for benchmarks and MLflow."""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from pathlib import Path

import click

from adapters.airflow import AirflowApiSource
from adapters.mlflow import MlflowExperimentAdapter
from workspaces.data_engineering.agents.prod_support import capture_day
from workspaces.data_engineering.benchmarks import default_catalog

DEFAULT_TRACKING_URI = "sqlite:///var/mlflow/backend.db"
DEFAULT_ARTIFACT_ROOT = Path("var/mlflow/artifacts")


@click.group()
def cli() -> None:
    """Manage data-engineering agents and benchmarks."""


@cli.command("benchmarks")
def list_benchmarks() -> None:
    """List benchmarks visible to the application."""
    for benchmark in default_catalog().list():
        click.echo(f"{benchmark.display_name}\t{benchmark.group}")


@cli.command("init")
@click.option(
    "--tracking-uri",
    default=DEFAULT_TRACKING_URI,
    show_default=True,
)
@click.option(
    "--artifact-root",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_ARTIFACT_ROOT,
    show_default=True,
)
def initialize(tracking_uri: str, artifact_root: Path) -> None:
    """Initialize MLflow and seed bundled benchmarks for the UI."""
    artifact_root.mkdir(parents=True, exist_ok=True)
    adapter = MlflowExperimentAdapter.from_tracking_uri(tracking_uri)
    artifact_uri = artifact_root.resolve().as_uri()
    for benchmark in default_catalog().list():
        run_id = adapter.seed_benchmark(
            benchmark,
            artifact_location=artifact_uri,
        )
        click.echo(f"{benchmark.display_name}\t{run_id}")


@cli.command("capture-prod-support")
@click.option(
    "--date",
    "operational_date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    required=True,
)
@click.option(
    "--output-root",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("var/benchmark_data/prod_support"),
    show_default=True,
)
def capture_prod_support(operational_date: datetime, output_root: Path) -> None:
    """Capture redacted Airflow evidence for one benchmark day."""
    target_date: date = operational_date.date()
    source = AirflowApiSource.from_environment()
    target = asyncio.run(
        capture_day(
            source,
            target_date,
            output_root / target_date.isoformat(),
        )
    )
    click.echo(str(target))


def main() -> None:
    """Run the application CLI."""
    cli()


if __name__ == "__main__":
    main()
