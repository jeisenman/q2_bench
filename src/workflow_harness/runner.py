"""Deterministic workflow runner with stage and authorization enforcement."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

from workflow_harness.models import (
    InputT,
    OutputT,
    SideEffectPolicy,
    WorkflowDefinition,
    WorkflowEvent,
    WorkflowEventKind,
    WorkflowRequest,
    WorkflowRunResult,
    WorkflowStageDefinition,
)
from workflow_harness.protocols import Workflow, WorkflowRecorder

StageOutputT = TypeVar("StageOutputT")


class WorkflowContractError(RuntimeError):
    """Raised when an implementation violates its workflow definition."""


class WorkflowAuthorizationError(PermissionError):
    """Raised when an approval-required stage is not authorized."""


class NullWorkflowRecorder:
    """Discard workflow events while preserving the recorder contract."""

    async def record(self, event: WorkflowEvent) -> None:
        """Discard one event."""
        del event


class InMemoryWorkflowRecorder:
    """Retain bounded workflow events for tests and local inspection."""

    def __init__(self) -> None:
        """Initialize an empty event collection."""
        self._events: list[WorkflowEvent] = []

    @property
    def events(self) -> tuple[WorkflowEvent, ...]:
        """Return recorded events in execution order."""
        return tuple(self._events)

    async def record(self, event: WorkflowEvent) -> None:
        """Append one immutable event."""
        self._events.append(event)


class WorkflowRunner:
    """Run typed workflows and validate their externally visible stages."""

    def __init__(self, recorder: WorkflowRecorder | None = None) -> None:
        """Initialize with an optional lifecycle recorder."""
        self._recorder = recorder or NullWorkflowRecorder()

    async def run(
        self,
        workflow: Workflow[InputT, OutputT],
        request: WorkflowRequest[InputT],
    ) -> WorkflowRunResult[OutputT]:
        """Execute a workflow and return its verified output metadata."""
        definition = workflow.definition
        self._validate_authorizations(definition, request.authorized_stages)
        context = _ExecutionContext(definition, request, self._recorder)
        await context.record(WorkflowEventKind.RUN_STARTED)
        try:
            output = await workflow.execute(request, context)
            _require_completed_stage(definition, context.completed_stages)
            await context.record(WorkflowEventKind.RUN_COMPLETED)
            return WorkflowRunResult(
                output=output,
                correlation_id=request.correlation_id,
                completed_stages=context.completed_stages,
                attributes=(
                    ("workflow_name", definition.name),
                    ("workflow_version", definition.version),
                    ("workflow_stage_count", len(context.completed_stages)),
                ),
            )
        except Exception as error:
            await context.record(
                WorkflowEventKind.RUN_FAILED,
                error_type=type(error).__name__,
            )
            raise

    @staticmethod
    def _validate_authorizations(
        definition: WorkflowDefinition,
        authorized_stages: frozenset[str],
    ) -> None:
        declared = {stage.name for stage in definition.stages}
        unknown = sorted(authorized_stages.difference(declared))
        if unknown:
            message = (
                f"workflow {definition.name!r} received authorization for unknown "
                f"stages: {', '.join(unknown)}"
            )
            raise WorkflowContractError(message)


class _ExecutionContext(Generic[InputT]):
    """Enforce one workflow definition during execution."""

    def __init__(
        self,
        definition: WorkflowDefinition,
        request: WorkflowRequest[InputT],
        recorder: WorkflowRecorder,
    ) -> None:
        self._definition = definition
        self._request = request
        self._recorder = recorder
        self._completed_stages: list[str] = []
        self._active_stage: str | None = None

    @property
    def completed_stages(self) -> tuple[str, ...]:
        """Return successfully completed stage names."""
        return tuple(self._completed_stages)

    async def run_stage(
        self,
        name: str,
        operation: Callable[[], Awaitable[StageOutputT]],
    ) -> StageOutputT:
        """Execute one declared stage after validating order and authorization."""
        stage = self._stage(name)
        self._validate_stage_order(name)
        if (
            stage.side_effect_policy is SideEffectPolicy.APPROVAL_REQUIRED
            and name not in self._request.authorized_stages
        ):
            message = f"workflow stage {name!r} requires explicit authorization"
            raise WorkflowAuthorizationError(message)
        self._active_stage = name
        await self.record(WorkflowEventKind.STAGE_STARTED, stage_name=name)
        try:
            output = await operation()
        except Exception as error:
            await self.record(
                WorkflowEventKind.STAGE_FAILED,
                stage_name=name,
                error_type=type(error).__name__,
            )
            raise
        finally:
            self._active_stage = None
        self._completed_stages.append(name)
        await self.record(WorkflowEventKind.STAGE_COMPLETED, stage_name=name)
        return output

    async def record(
        self,
        kind: WorkflowEventKind,
        *,
        stage_name: str | None = None,
        error_type: str | None = None,
    ) -> None:
        """Record one bounded event using the current workflow identity."""
        await self._recorder.record(
            WorkflowEvent(
                kind=kind,
                workflow_name=self._definition.name,
                workflow_version=self._definition.version,
                correlation_id=self._request.correlation_id,
                stage_name=stage_name,
                error_type=error_type,
            )
        )

    def _stage(self, name: str) -> WorkflowStageDefinition:
        for stage in self._definition.stages:
            if stage.name == name:
                return stage
        message = f"workflow {self._definition.name!r} does not declare stage {name!r}"
        raise WorkflowContractError(message)

    def _validate_stage_order(self, name: str) -> None:
        if self._active_stage is not None:
            message = f"workflow stage {self._active_stage!r} is already running"
            raise WorkflowContractError(message)
        if name in self._completed_stages:
            message = f"workflow stage {name!r} cannot run more than once"
            raise WorkflowContractError(message)
        declared_order = tuple(stage.name for stage in self._definition.stages)
        current_index = declared_order.index(name)
        if self._completed_stages:
            previous_index = declared_order.index(self._completed_stages[-1])
            if current_index <= previous_index:
                message = f"workflow stage {name!r} violates declared stage order"
                raise WorkflowContractError(message)


def _require_completed_stage(
    definition: WorkflowDefinition,
    completed_stages: tuple[str, ...],
) -> None:
    if completed_stages:
        return
    message = f"workflow {definition.name!r} completed without running a stage"
    raise WorkflowContractError(message)
