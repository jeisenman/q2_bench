"""Local application commands for benchmarks and MLflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import click

from adapters.inbound import MatrixInboundAdapter
from adapters.mlflow import (
    BedrockAssistantConfigurator,
    CodexAssistantConfigurator,
    MlflowExperimentAdapter,
    UrlJsonTransport,
    load_recorded_evaluation,
    publish_matrix_results,
    publish_recorded_evaluation,
    register_agent_definitions,
)
from cli.deployment import approve_deployment
from cli.mlflow import configure_codex_tracing
from cli.prod_support_collection import (
    capture_prod_support,
    debug_prod_support,
)
from cli.prod_support_evidence import summarize_prod_support_evidence
from cli.prod_support_replay import (
    load_replay_case,
    run_replay_case,
    write_recorded_outcome,
)
from cli.setup import setup
from cli.skills import sync_skills
from workspaces.data_engineering.benchmarks import (
    default_catalog,
    load_matrix_run,
)
from workspaces.data_engineering.workflows.prod_support import (
    PROD_SUPPORT_MLFLOW_NAMESPACE,
    PRODUCTION_SUPPORT_WORKFLOW_DEFINITIONS,
)

DEFAULT_TRACKING_URI = "sqlite:///var/mlflow/backend.db"
DEFAULT_ARTIFACT_ROOT = Path("var/mlflow/artifacts")
PROD_SUPPORT_CASES = Path(
    "src/workspaces/data_engineering/benchmarks/deprecated/"
    "production_support/dates/09-27-26/cases.yaml"
)
DEFAULT_ASSISTANT_CONFIG = Path.home() / ".mlflow/assistant/config.json"
DEFAULT_AGENT_CONFIGURATIONS = Path(
    "src/workspaces/data_engineering/benchmarks/agent-manifest.yaml"
)
DEFAULT_MATRIX_BENCHMARK = Path(
    "src/workspaces/data_engineering/benchmarks/deprecated/production_support/"
    "dates/09-27-26/evaluation.yaml"
)
DEFAULT_MATRIX_CASES = Path(
    "src/workspaces/data_engineering/benchmarks/deprecated/production_support/"
    "dates/09-27-26/cases.yaml"
)
DEFAULT_MATRIX_CASE = "prod-support-us-ca-operational-2026-09-26"


@click.group()
def cli() -> None:
    """Manage data-engineering agents and benchmarks."""


cli.add_command(sync_skills)
cli.add_command(approve_deployment)
cli.add_command(capture_prod_support)
cli.add_command(debug_prod_support)
cli.add_command(setup)


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


@cli.command("register-agent")
@click.argument("agent", type=click.Choice(["prod-support"]))
@click.option("--tracking-uri", default=DEFAULT_TRACKING_URI, show_default=True)
def register_agent(agent: str, tracking_uri: str) -> None:
    """Register an agent family in its MLflow namespace."""
    del agent
    registrations = register_agent_definitions(
        PRODUCTION_SUPPORT_WORKFLOW_DEFINITIONS,
        tracking_uri=tracking_uri,
        experiment_name="production_operations",
        namespace=PROD_SUPPORT_MLFLOW_NAMESPACE,
    )
    for definition, run_id, version in registrations:
        click.echo(
            f"{PROD_SUPPORT_MLFLOW_NAMESPACE}.{definition.name}\t"
            f"v{definition.version}\t{version}\t{run_id}"
        )


@cli.command("configure-assistant")
@click.option("--tracking-uri", default="http://mlflow:5000", show_default=True)
@click.option(
    "--provider",
    type=click.Choice(["codex", "bedrock"]),
    default="codex",
    show_default=True,
)
@click.option(
    "--model",
    default=None,
    help="Provider model; Codex defaults to its configured model.",
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
    provider: str,
    model: str | None,
    region: str,
    config_path: Path,
) -> None:
    """Configure the selected MLflow UI assistant provider."""
    if provider == "codex":
        selected_model = model or "default"
        selected = CodexAssistantConfigurator().configure(
            model=selected_model,
            config_path=config_path,
        )
    else:
        selected_model = model or "us.anthropic.claude-sonnet-4-6"
        selected = BedrockAssistantConfigurator(
            UrlJsonTransport(tracking_uri)
        ).configure(
            model=selected_model,
            region=region,
            config_path=config_path,
        )
    click.echo(f"{selected}\t{selected_model}\t{config_path}")


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


@cli.command("run-matrix")
@click.option(
    "--benchmark",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DEFAULT_MATRIX_BENCHMARK,
    show_default=True,
)
@click.option(
    "--agent-manifest",
    "agent_manifest",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DEFAULT_AGENT_CONFIGURATIONS,
    show_default=True,
)
@click.option(
    "--cases",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DEFAULT_MATRIX_CASES,
    show_default=True,
)
@click.option("--case", "case_id", default=DEFAULT_MATRIX_CASE, show_default=True)
@click.option(
    "--configuration",
    "configuration_ids",
    multiple=True,
    help="Registered agent configuration to run; repeat to compare selected profiles.",
)
@click.option(
    "--execute/--dry-run",
    default=False,
    help="Invoke configured Codex candidates and judge; default prints the plan.",
)
@click.option("--tracking-uri", default=DEFAULT_TRACKING_URI, show_default=True)
def run_benchmark_matrix(**values: object) -> None:
    """Run or inspect a grouped prod-support model matrix."""
    benchmark = cast(Path, values["benchmark"])
    agent_manifest = cast(Path, values["agent_manifest"])
    cases = cast(Path, values["cases"])
    case_id = cast(str, values["case_id"])
    configuration_ids = cast(tuple[str, ...], values["configuration_ids"])
    execute = cast(bool, values["execute"])
    tracking_uri = cast(str, values["tracking_uri"])
    configured = load_matrix_run(
        benchmark,
        agent_manifest,
        cases,
        case_id,
        configuration_ids,
    )
    adapter = MatrixInboundAdapter(Path.cwd())
    if not execute:
        for planned_run in adapter.plan(configured):
            click.echo(json.dumps(planned_run, sort_keys=True))
        return
    results = adapter.run(configured)
    parent_run_id = publish_matrix_results(
        configured,
        results,
        tracking_uri=tracking_uri,
    )
    click.echo(f"matrix\t{configured.matrix_id}\t{parent_run_id}")
    for judged_run in sorted(
        results,
        key=lambda value: value.overall_score,
        reverse=True,
    ):
        click.echo(
            f"{judged_run.candidate.profile}\t{judged_run.overall_score:.3f}\t"
            f"{judged_run.candidate.elapsed_seconds:.2f}s\t"
            f"{judged_run.candidate.output_tokens} output tokens"
        )


def main() -> None:
    """Run the application CLI."""
    cli()


cli.add_command(configure_codex_tracing)
cli.add_command(summarize_prod_support_evidence)


if __name__ == "__main__":
    main()
