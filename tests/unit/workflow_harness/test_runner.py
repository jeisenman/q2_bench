from __future__ import annotations

import asyncio

import pytest

from workflow_harness import (
    InMemoryWorkflowRecorder,
    SideEffectPolicy,
    WorkflowAuthorizationError,
    WorkflowContractError,
    WorkflowDefinition,
    WorkflowEventKind,
    WorkflowRequest,
    WorkflowRunner,
    WorkflowStageDefinition,
)


class ExampleWorkflow:
    definition = WorkflowDefinition(
        name="example",
        description="Run an example.",
        version="2",
        stages=(
            WorkflowStageDefinition(
                name="inspect",
                description="Inspect input.",
            ),
            WorkflowStageDefinition(
                name="change",
                description="Apply an approved change.",
                side_effect_policy=SideEffectPolicy.APPROVAL_REQUIRED,
            ),
        ),
    )

    async def execute(self, request, context):
        inspected = await context.run_stage(
            "inspect",
            lambda: _value(f"inspected:{request.input}"),
        )
        if "change" not in request.authorized_stages:
            return inspected
        return await context.run_stage(
            "change",
            lambda: _value(f"changed:{inspected}"),
        )


async def _value(value: str) -> str:
    return value


def test_runner_records_successful_read_only_workflow() -> None:
    recorder = InMemoryWorkflowRecorder()
    result = asyncio.run(
        WorkflowRunner(recorder).run(
            ExampleWorkflow(),
            WorkflowRequest(input="data", correlation_id="run-1"),
        )
    )

    assert result.output == "inspected:data"
    assert result.completed_stages == ("inspect",)
    assert dict(result.attributes) == {
        "workflow_name": "example",
        "workflow_version": "2",
        "workflow_stage_count": 1,
    }
    assert tuple(event.kind for event in recorder.events) == (
        WorkflowEventKind.RUN_STARTED,
        WorkflowEventKind.STAGE_STARTED,
        WorkflowEventKind.STAGE_COMPLETED,
        WorkflowEventKind.RUN_COMPLETED,
    )


def test_runner_executes_explicitly_authorized_mutating_stage() -> None:
    result = asyncio.run(
        WorkflowRunner().run(
            ExampleWorkflow(),
            WorkflowRequest(
                input="data",
                correlation_id="run-2",
                authorized_stages=frozenset({"change"}),
            ),
        )
    )

    assert result.output == "changed:inspected:data"
    assert result.completed_stages == ("inspect", "change")


def test_context_rejects_unauthorized_mutating_stage() -> None:
    class UnsafeWorkflow(ExampleWorkflow):
        async def execute(self, request, context):
            del request
            return await context.run_stage("change", lambda: _value("changed"))

    with pytest.raises(WorkflowAuthorizationError, match="explicit authorization"):
        asyncio.run(
            WorkflowRunner().run(
                UnsafeWorkflow(),
                WorkflowRequest(input="data", correlation_id="run-3"),
            )
        )


def test_runner_rejects_authorization_for_unknown_stage() -> None:
    with pytest.raises(WorkflowContractError, match="unknown stages"):
        asyncio.run(
            WorkflowRunner().run(
                ExampleWorkflow(),
                WorkflowRequest(
                    input="data",
                    correlation_id="run-4",
                    authorized_stages=frozenset({"missing"}),
                ),
            )
        )


def test_runner_rejects_workflow_that_runs_no_stage() -> None:
    class EmptyWorkflow(ExampleWorkflow):
        async def execute(self, request, context):
            del request, context
            return "empty"

    recorder = InMemoryWorkflowRecorder()
    with pytest.raises(WorkflowContractError, match="without running a stage"):
        asyncio.run(
            WorkflowRunner(recorder).run(
                EmptyWorkflow(),
                WorkflowRequest(input="data", correlation_id="run-5"),
            )
        )

    assert recorder.events[-1].kind is WorkflowEventKind.RUN_FAILED


def test_runner_records_stage_and_run_failure() -> None:
    class FailingWorkflow(ExampleWorkflow):
        async def execute(self, request, context):
            del request

            async def fail() -> str:
                raise RuntimeError("failure")

            return await context.run_stage("inspect", fail)

    recorder = InMemoryWorkflowRecorder()
    with pytest.raises(RuntimeError, match="failure"):
        asyncio.run(
            WorkflowRunner(recorder).run(
                FailingWorkflow(),
                WorkflowRequest(input="data", correlation_id="run-6"),
            )
        )

    assert tuple(event.kind for event in recorder.events[-2:]) == (
        WorkflowEventKind.STAGE_FAILED,
        WorkflowEventKind.RUN_FAILED,
    )
    assert recorder.events[-1].error_type == "RuntimeError"
