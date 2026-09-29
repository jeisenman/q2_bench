"""Runtime protocols for provider-neutral workflow execution."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar

from workflow_harness.models import WorkflowDefinition, WorkflowEvent, WorkflowRequest

StageOutputT = TypeVar("StageOutputT")
WorkflowInputT = TypeVar("WorkflowInputT")
WorkflowOutputT_co = TypeVar("WorkflowOutputT_co", covariant=True)


class WorkflowExecutionContext(Protocol):
    """Run declared stages with policy enforcement and lifecycle recording."""

    async def run_stage(
        self,
        name: str,
        operation: Callable[[], Awaitable[StageOutputT]],
    ) -> StageOutputT:
        """Execute one declared stage."""
        ...


class Workflow(Protocol[WorkflowInputT, WorkflowOutputT_co]):
    """Expose a workflow definition and execute a typed request."""

    @property
    def definition(self) -> WorkflowDefinition:
        """Return immutable workflow metadata."""
        ...

    async def execute(
        self,
        request: WorkflowRequest[WorkflowInputT],
        context: WorkflowExecutionContext,
    ) -> WorkflowOutputT_co:
        """Execute the workflow through the supplied context."""
        ...


class WorkflowRecorder(Protocol):
    """Persist bounded workflow lifecycle events."""

    async def record(self, event: WorkflowEvent) -> None:
        """Record one lifecycle event."""
        ...
