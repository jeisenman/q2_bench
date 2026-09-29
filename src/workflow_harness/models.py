"""Immutable contracts for defining and running typed workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Generic, TypeVar

from domain import Scalar

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")
Attributes = tuple[tuple[str, Scalar], ...]


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        message = f"{field_name} must not be empty"
        raise ValueError(message)


class SideEffectPolicy(StrEnum):
    """Describe whether a workflow stage requires explicit authorization."""

    READ_ONLY = "read_only"
    APPROVAL_REQUIRED = "approval_required"


class WorkflowEventKind(StrEnum):
    """Identify bounded workflow lifecycle events."""

    RUN_STARTED = "run.started"
    STAGE_STARTED = "stage.started"
    STAGE_COMPLETED = "stage.completed"
    STAGE_FAILED = "stage.failed"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"


@dataclass(frozen=True, slots=True)
class WorkflowCapabilityDefinition:
    """Describe one external capability available to a workflow."""

    name: str
    description: str
    side_effect_policy: SideEffectPolicy = SideEffectPolicy.READ_ONLY

    def __post_init__(self) -> None:
        """Validate required capability metadata."""
        _require_text(self.name, "capability name")
        _require_text(self.description, "capability description")


@dataclass(frozen=True, slots=True)
class WorkflowStageDefinition:
    """Describe one ordered workflow stage and its capability dependencies."""

    name: str
    description: str
    capabilities: tuple[str, ...] = ()
    side_effect_policy: SideEffectPolicy = SideEffectPolicy.READ_ONLY

    def __post_init__(self) -> None:
        """Validate required stage metadata."""
        _require_text(self.name, "stage name")
        _require_text(self.description, "stage description")
        if len(self.capabilities) != len(set(self.capabilities)):
            message = f"stage {self.name!r} contains duplicate capabilities"
            raise ValueError(message)
        for capability in self.capabilities:
            _require_text(capability, "stage capability")


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    """Describe a versioned workflow independently of its runtime."""

    name: str
    description: str
    version: str
    stages: tuple[WorkflowStageDefinition, ...]
    capabilities: tuple[WorkflowCapabilityDefinition, ...] = ()

    def __post_init__(self) -> None:
        """Validate workflow structure and capability references."""
        _require_text(self.name, "workflow name")
        _require_text(self.description, "workflow description")
        _require_text(self.version, "workflow version")
        if not self.stages:
            message = f"workflow {self.name!r} must define at least one stage"
            raise ValueError(message)
        stage_names = tuple(stage.name for stage in self.stages)
        if len(stage_names) != len(set(stage_names)):
            message = f"workflow {self.name!r} contains duplicate stage names"
            raise ValueError(message)
        capability_names = tuple(capability.name for capability in self.capabilities)
        if len(capability_names) != len(set(capability_names)):
            message = f"workflow {self.name!r} contains duplicate capabilities"
            raise ValueError(message)
        capabilities_by_name = {
            capability.name: capability for capability in self.capabilities
        }
        for stage in self.stages:
            unknown = tuple(
                name for name in stage.capabilities if name not in capabilities_by_name
            )
            if unknown:
                message = (
                    f"stage {stage.name!r} references unknown capabilities: "
                    f"{', '.join(unknown)}"
                )
                raise ValueError(message)
            mutating = tuple(
                name
                for name in stage.capabilities
                if capabilities_by_name[name].side_effect_policy
                is SideEffectPolicy.APPROVAL_REQUIRED
            )
            if mutating and stage.side_effect_policy is SideEffectPolicy.READ_ONLY:
                message = (
                    f"read-only stage {stage.name!r} references approval-required "
                    f"capabilities: {', '.join(mutating)}"
                )
                raise ValueError(message)


@dataclass(frozen=True, slots=True)
class WorkflowRequest(Generic[InputT]):
    """Represent one typed workflow invocation."""

    input: InputT
    correlation_id: str
    attributes: Attributes = ()
    authorized_stages: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        """Validate request correlation and authorization values."""
        _require_text(self.correlation_id, "correlation_id")
        for stage_name in self.authorized_stages:
            _require_text(stage_name, "authorized stage")


@dataclass(frozen=True, slots=True)
class WorkflowRunResult(Generic[OutputT]):
    """Return typed output and verified workflow execution metadata."""

    output: OutputT
    correlation_id: str
    completed_stages: tuple[str, ...]
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        """Validate result correlation and completed-stage uniqueness."""
        _require_text(self.correlation_id, "correlation_id")
        if len(self.completed_stages) != len(set(self.completed_stages)):
            message = "completed_stages must not contain duplicates"
            raise ValueError(message)


@dataclass(frozen=True, slots=True)
class WorkflowEvent:
    """Record bounded workflow lifecycle metadata without payloads."""

    kind: WorkflowEventKind
    workflow_name: str
    workflow_version: str
    correlation_id: str
    stage_name: str | None = None
    error_type: str | None = None

    def __post_init__(self) -> None:
        """Validate required event identifiers."""
        _require_text(self.workflow_name, "workflow_name")
        _require_text(self.workflow_version, "workflow_version")
        _require_text(self.correlation_id, "correlation_id")
        if self.stage_name is not None:
            _require_text(self.stage_name, "stage_name")
        if self.error_type is not None:
            _require_text(self.error_type, "error_type")
