"""Register immutable agent definitions in MLflow."""

from __future__ import annotations

from dataclasses import asdict
from importlib import import_module

from domain import AgentDefinition


def register_agent_definition(
    definition: AgentDefinition,
    *,
    tracking_uri: str,
    experiment_name: str,
) -> tuple[str, str]:
    """Log an agent definition and create its MLflow model-registry version."""
    mlflow = import_module("mlflow")
    client_module = import_module("mlflow.tracking")
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)
    registered_name = definition.name
    with mlflow.start_run(
        run_name=f"{registered_name}-v{definition.version}",
        tags={
            "agent.name": registered_name,
            "agent.version": definition.version,
        },
    ) as run:
        mlflow.log_dict(asdict(definition), "agent/definition.json")
        run_id = str(run.info.run_id)
    client = client_module.MlflowClient()
    registered = client.search_registered_models(
        filter_string=f"name = '{registered_name}'",
    )
    if not registered:
        client.create_registered_model(registered_name)
    version = client.create_model_version(
        name=registered_name,
        source=f"runs:/{run_id}/agent",
        run_id=run_id,
        tags={"agent.version": definition.version},
    )
    client.set_registered_model_alias(
        registered_name,
        f"agent-v{definition.version}",
        version.version,
    )
    return run_id, str(version.version)
