"""Local application commands for benchmarks and MLflow."""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from pathlib import Path

import click

from adapters.airflow import AirflowApiSource
from adapters.mlflow import (
    BedrockAssistantConfigurator,
    MlflowExperimentAdapter,
    UrlJsonTransport,
    load_recorded_evaluation,
    publish_recorded_evaluation,
)
from cli.prod_support_replay import (
    load_replay_case,
    run_replay_case,
    write_recorded_outcome,
)
from workspaces.data_engineering.agents.prod_support import capture_day
from workspaces.data_engineering.benchmarks import default_catalog

DEFAULT_TRACKING_URI = "sqlite:///var/mlflow/backend.db"
DEFAULT_ARTIFACT_ROOT = Path("var/mlflow/artifacts")
PROD_SUPPORT_CASES = Path(
    "src/workspaces/data_engineering/benchmarks/"
    "production_support/dates/09-25-26/cases.yaml"
)
DEFAULT_ASSISTANT_CONFIG = Path.home() / ".mlflow/assistant/config.json"


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


@cli.command("configure-assistant")
@click.option("--tracking-uri", default="http://mlflow:5000", show_default=True)
@click.option(
    "--model",
    default="us.anthropic.claude-sonnet-4-6",
    show_default=True,
)
@click.option("--region", default="us-east-2", show_default=True)
@click.option(
    "--config-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DEFAULT_ASSISTANT_CONFIG,
    show_default=True,
)
def configure_assistant(
    tracking_uri: str,
    model: str,
    region: str,
    config_path: Path,
) -> None:
    """Configure the MLflow UI assistant to use Amazon Bedrock."""
    configurator = BedrockAssistantConfigurator(UrlJsonTransport(tracking_uri))
    endpoint = configurator.configure(
        model=model,
        region=region,
        config_path=config_path,
    )
    click.echo(f"{endpoint}\t{model}\t{config_path}")


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


@cli.command("evaluate")
@click.argument("benchmark", type=click.Choice(["prod-support"]))
@click.option("--case", "case_id", required=True)
@click.option(
    "--recorded-result",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
)
@click.option("--tracking-uri", default=DEFAULT_TRACKING_URI, show_default=True)
def evaluate_benchmark(
    benchmark: str,
    case_id: str,
    recorded_result: Path,
    tracking_uri: str,
) -> None:
    """Publish a recorded benchmark case to the MLflow Evaluations view."""
    del benchmark
    evaluation = load_recorded_evaluation(
        PROD_SUPPORT_CASES,
        case_id,
        recorded_result,
    )
    run_id = publish_recorded_evaluation(
        evaluation,
        experiment_name="production_operations",
        tracking_uri=tracking_uri,
    )
    click.echo(f"{case_id}\t{run_id}")


@cli.command("replay-evaluate")
@click.argument("benchmark", type=click.Choice(["prod-support"]))
@click.option("--case", "case_id", required=True)
@click.option(
    "--dataset",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
)
@click.option("--tracking-uri", default=DEFAULT_TRACKING_URI, show_default=True)
def replay_evaluate_benchmark(
    benchmark: str,
    case_id: str,
    dataset: Path,
    output: Path | None,
    tracking_uri: str,
) -> None:
    """Run one curated replay case and publish its MLflow evaluation."""
    del benchmark
    case = load_replay_case(PROD_SUPPORT_CASES, case_id)
    outcome = run_replay_case(case, dataset)
    result_path = output or Path("var/mlflow/evaluations") / f"{case_id}.json"
    write_recorded_outcome(outcome, result_path)
    evaluation = load_recorded_evaluation(
        PROD_SUPPORT_CASES,
        case_id,
        result_path,
    )
    run_id = publish_recorded_evaluation(
        evaluation,
        experiment_name="production_operations",
        tracking_uri=tracking_uri,
    )
    click.echo(f"{case_id}\t{run_id}\t{result_path}")


def main() -> None:
    """Run the application CLI."""
    cli()


if __name__ == "__main__":
    main()
