from __future__ import annotations

from types import SimpleNamespace
from typing import ClassVar

import pytest

from adapters.mlflow import WorkflowRunPublishConfig, workflow_runs
from workflow_harness import (
    WorkflowDefinition,
    WorkflowEvent,
    WorkflowEventKind,
    WorkflowRunResult,
    WorkflowStageDefinition,
)

DEFINITION = WorkflowDefinition(
    name="upgrade-python",
    description="Upgrade a Python project.",
    version="3",
    stages=(
        WorkflowStageDefinition(
            name="inventory",
            description="Inspect the project.",
        ),
    ),
)


def _event(kind: WorkflowEventKind, stage_name: str | None = None) -> WorkflowEvent:
    return WorkflowEvent(
        kind=kind,
        workflow_name=DEFINITION.name,
        workflow_version=DEFINITION.version,
        correlation_id="upgrade-1",
        stage_name=stage_name,
    )


EVENTS = (
    _event(WorkflowEventKind.RUN_STARTED),
    _event(WorkflowEventKind.STAGE_STARTED, "inventory"),
    _event(WorkflowEventKind.STAGE_COMPLETED, "inventory"),
    _event(WorkflowEventKind.RUN_COMPLETED),
)
RESULT = WorkflowRunResult(
    output={"ignored": "payload"},
    correlation_id="upgrade-1",
    completed_stages=("inventory",),
)


class FakeRun:
    def __enter__(self):
        return SimpleNamespace(info=SimpleNamespace(run_id="workflow-run-1"))

    def __exit__(self, *_args):
        return None


class FakeMlflow:
    logged: ClassVar[dict[str, object]] = {}

    @classmethod
    def set_tracking_uri(cls, value):
        cls.logged["tracking_uri"] = value

    @classmethod
    def set_experiment(cls, value):
        cls.logged["experiment"] = value

    @classmethod
    def start_run(cls, **kwargs):
        cls.logged["run"] = kwargs
        return FakeRun()

    @classmethod
    def log_params(cls, value):
        cls.logged["params"] = value

    @classmethod
    def log_metrics(cls, value):
        cls.logged["metrics"] = value

    @classmethod
    def log_dict(cls, value, path):
        cls.logged["artifact"] = (value, path)


def test_publishes_bounded_workflow_metadata(monkeypatch) -> None:
    FakeMlflow.logged = {}
    monkeypatch.setattr(workflow_runs, "import_module", lambda _name: FakeMlflow)

    run_id = workflow_runs.publish_workflow_run(
        DEFINITION,
        RESULT,
        EVENTS,
        WorkflowRunPublishConfig(
            tracking_uri="http://localhost:5000",
            experiment_name="workflow-benchmarks",
            tags=(("benchmark.case_id", "case-1"),),
        ),
    )

    assert run_id == "workflow-run-1"
    assert FakeMlflow.logged["metrics"] == {
        "workflow.stage_count": 1.0,
        "workflow.event_count": 4.0,
    }
    artifact, path = FakeMlflow.logged["artifact"]
    assert path == "workflow/run.json"
    assert artifact["completed_stages"] == ["inventory"]
    assert "output" not in artifact
    assert FakeMlflow.logged["run"]["tags"]["benchmark.case_id"] == "case-1"


@pytest.mark.parametrize(
    ("events", "message"),
    [
        ((), "at least one"),
        (EVENTS[1:], "begin"),
        (EVENTS[:-1], "end"),
        (
            (
                _event(WorkflowEventKind.RUN_STARTED),
                _event(WorkflowEventKind.RUN_COMPLETED),
            ),
            "completed workflow stages",
        ),
    ],
)
def test_rejects_inconsistent_workflow_events(events, message) -> None:
    with pytest.raises(workflow_runs.WorkflowRunPublishError, match=message):
        workflow_runs.publish_workflow_run(
            DEFINITION,
            RESULT,
            events,
            WorkflowRunPublishConfig(
                tracking_uri="sqlite:///mlflow.db",
                experiment_name="workflow-benchmarks",
            ),
        )


def test_rejects_mismatched_workflow_identity() -> None:
    mismatched = (
        WorkflowEvent(
            kind=WorkflowEventKind.RUN_STARTED,
            workflow_name="other",
            workflow_version="3",
            correlation_id="upgrade-1",
        ),
        *EVENTS[1:],
    )

    with pytest.raises(workflow_runs.WorkflowRunPublishError, match="identity"):
        workflow_runs.publish_workflow_run(
            DEFINITION,
            RESULT,
            mismatched,
            WorkflowRunPublishConfig(
                tracking_uri="sqlite:///mlflow.db",
                experiment_name="workflow-benchmarks",
            ),
        )
