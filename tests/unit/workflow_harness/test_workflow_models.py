from __future__ import annotations

import pytest

from workflow_harness import (
    SideEffectPolicy,
    WorkflowCapabilityDefinition,
    WorkflowDefinition,
    WorkflowRequest,
    WorkflowStageDefinition,
)


def test_workflow_definition_accepts_declared_capabilities() -> None:
    definition = WorkflowDefinition(
        name="support",
        description="Investigate failures.",
        version="1",
        capabilities=(
            WorkflowCapabilityDefinition(
                name="airflow.read",
                description="Read Airflow.",
            ),
        ),
        stages=(
            WorkflowStageDefinition(
                name="investigate",
                description="Investigate failures.",
                capabilities=("airflow.read",),
            ),
        ),
    )

    assert definition.stages[0].capabilities == ("airflow.read",)


def test_workflow_definition_rejects_unknown_capability() -> None:
    with pytest.raises(ValueError, match="unknown capabilities"):
        WorkflowDefinition(
            name="support",
            description="Investigate failures.",
            version="1",
            stages=(
                WorkflowStageDefinition(
                    name="investigate",
                    description="Investigate failures.",
                    capabilities=("airflow.read",),
                ),
            ),
        )


def test_read_only_stage_rejects_mutating_capability() -> None:
    with pytest.raises(ValueError, match="read-only stage"):
        WorkflowDefinition(
            name="support",
            description="Retry failures.",
            version="1",
            capabilities=(
                WorkflowCapabilityDefinition(
                    name="airflow.retry",
                    description="Retry Airflow tasks.",
                    side_effect_policy=SideEffectPolicy.APPROVAL_REQUIRED,
                ),
            ),
            stages=(
                WorkflowStageDefinition(
                    name="retry",
                    description="Retry failures.",
                    capabilities=("airflow.retry",),
                ),
            ),
        )


def test_workflow_request_rejects_empty_correlation_id() -> None:
    with pytest.raises(ValueError, match="correlation_id"):
        WorkflowRequest(input="request", correlation_id=" ")
