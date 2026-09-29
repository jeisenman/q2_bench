"""Publish bounded workflow-harness metadata to MLflow Tracking."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import import_module

from workflow_harness import (
    WorkflowDefinition,
    WorkflowEvent,
    WorkflowEventKind,
    WorkflowRunResult,
)


class WorkflowRunPublishError(ValueError):
    """Raised when workflow metadata is inconsistent or incomplete."""


@dataclass(frozen=True, slots=True)
class WorkflowRunPublishConfig:
    """Configure the MLflow destination and searchable run metadata."""

    tracking_uri: str
    experiment_name: str
    run_name: str | None = None
    tags: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        """Reject incomplete destinations and duplicate tag names."""
        if not self.tracking_uri.strip():
            message = "MLflow tracking_uri must not be empty"
            raise ValueError(message)
        if not self.experiment_name.strip():
            message = "MLflow experiment_name must not be empty"
            raise ValueError(message)
        if self.run_name is not None and not self.run_name.strip():
            message = "MLflow run_name must not be empty"
            raise ValueError(message)
        names = tuple(name for name, _value in self.tags)
        if len(names) != len(set(names)):
            message = "MLflow workflow tags must have unique names"
            raise ValueError(message)


def publish_workflow_run(
    definition: WorkflowDefinition,
    result: WorkflowRunResult[object],
    events: tuple[WorkflowEvent, ...],
    config: WorkflowRunPublishConfig,
) -> str:
    """Publish one successful workflow run without logging its payload."""
    _validate_run(definition, result, events)
    mlflow = import_module("mlflow")
    mlflow.set_tracking_uri(config.tracking_uri)
    mlflow.set_experiment(config.experiment_name)
    run_tags = {
        "workflow.name": definition.name,
        "workflow.version": definition.version,
        "workflow.correlation_id": result.correlation_id,
        **dict(config.tags),
    }
    with mlflow.start_run(
        run_name=config.run_name or f"{definition.name}-v{definition.version}",
        tags=run_tags,
    ) as run:
        mlflow.log_params(
            {
                "workflow.name": definition.name,
                "workflow.version": definition.version,
                "workflow.completed_stages": ",".join(result.completed_stages),
            }
        )
        mlflow.log_metrics(
            {
                "workflow.stage_count": float(len(result.completed_stages)),
                "workflow.event_count": float(len(events)),
            }
        )
        mlflow.log_dict(
            {
                "workflow": {
                    "name": definition.name,
                    "version": definition.version,
                },
                "correlation_id": result.correlation_id,
                "completed_stages": list(result.completed_stages),
                "events": [asdict(event) for event in events],
            },
            "workflow/run.json",
        )
        return str(run.info.run_id)


def _validate_run(
    definition: WorkflowDefinition,
    result: WorkflowRunResult[object],
    events: tuple[WorkflowEvent, ...],
) -> None:
    if not events:
        message = "workflow run requires at least one lifecycle event"
        raise WorkflowRunPublishError(message)
    mismatched = tuple(
        event
        for event in events
        if event.workflow_name != definition.name
        or event.workflow_version != definition.version
        or event.correlation_id != result.correlation_id
    )
    if mismatched:
        message = "workflow events do not match the published run identity"
        raise WorkflowRunPublishError(message)
    if events[0].kind is not WorkflowEventKind.RUN_STARTED:
        message = "workflow events must begin with run.started"
        raise WorkflowRunPublishError(message)
    if events[-1].kind is not WorkflowEventKind.RUN_COMPLETED:
        message = "successful workflow events must end with run.completed"
        raise WorkflowRunPublishError(message)
    completed = tuple(
        event.stage_name
        for event in events
        if event.kind is WorkflowEventKind.STAGE_COMPLETED
        and event.stage_name is not None
    )
    if completed != result.completed_stages:
        message = "completed workflow stages do not match lifecycle events"
        raise WorkflowRunPublishError(message)
