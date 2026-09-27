"""MCP-safe production-support follow-up planning and execution."""

from __future__ import annotations

import os

from adapters.airflow import AirflowApiSource
from workspaces.data_engineering.agents.production_support import (
    FollowUpAgent,
    Region,
    RetryCandidate,
    RetryPlan,
)

SOURCE_ENV = "PROD_SUPPORT_SOURCE"


class FollowUpToolError(ValueError):
    """Raised for invalid follow-up tool inputs or state."""

    @classmethod
    def invalid_candidate(cls) -> FollowUpToolError:
        """Return an error for malformed retry candidate input."""
        return cls("invalid prod-support retry candidate")

    @classmethod
    def plan_mismatch(cls) -> FollowUpToolError:
        """Return an error when approval does not match the dry run."""
        return cls("approved plan ID does not match the current dry-run plan")


class FollowUpConfigurationError(RuntimeError):
    """Raised when production retry configuration is unavailable."""

    @classmethod
    def production_required(cls) -> FollowUpConfigurationError:
        """Return an error when retries are not in production mode."""
        return cls(
            "prod-support follow-up retries require PROD_SUPPORT_SOURCE=production"
        )


def candidate_output(candidate: RetryCandidate) -> dict[str, object]:
    """Serialize one safe retry candidate for MCP clients."""
    return {
        "number": candidate.number,
        "region": candidate.region.value,
        "dag_id": candidate.dag_id,
        "run_id": candidate.run_id,
        "task_id": candidate.task_id,
        "label": candidate.label,
    }


def candidate_input(value: dict[str, object]) -> RetryCandidate:
    """Validate one retry candidate returned by run_prod_support."""
    number = value.get("number")
    if not isinstance(number, int):
        raise FollowUpToolError.invalid_candidate()
    try:
        return RetryCandidate(
            number=number,
            region=Region(str(value["region"])),
            dag_id=str(value["dag_id"]),
            run_id=str(value["run_id"]),
            task_id=str(value["task_id"]),
            label=str(value["label"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise FollowUpToolError.invalid_candidate() from error


async def plan_prod_support_follow_up(
    direction: str,
    retry_candidates: list[dict[str, object]],
) -> dict[str, object]:
    """Return an exact Airflow retry plan without mutating production."""
    candidates = tuple(candidate_input(item) for item in retry_candidates)
    return _plan_output(await _follow_up_agent().plan(direction, candidates))


async def execute_prod_support_follow_up(
    direction: str,
    retry_candidates: list[dict[str, object]],
    plan_id: str,
    approval_id: str,
) -> dict[str, object]:
    """Revalidate and execute an operator-approved retry plan."""
    candidates = tuple(candidate_input(item) for item in retry_candidates)
    agent = _follow_up_agent()
    plan = await agent.plan(direction, candidates)
    if plan.plan_id != plan_id:
        raise FollowUpToolError.plan_mismatch()
    states = await agent.execute(plan, approval_id)
    return {
        "plan_id": plan.plan_id,
        "approval_id": approval_id,
        "task_instances": [
            {
                "region": item.region.value,
                "dag_id": item.dag_id,
                "run_id": item.run_id,
                "task_id": item.task_id,
                "state": item.state,
            }
            for item in states
        ],
    }


def _follow_up_agent() -> FollowUpAgent:
    if os.environ.get(SOURCE_ENV) != "production":
        raise FollowUpConfigurationError.production_required()
    return FollowUpAgent(AirflowApiSource.from_environment())


def _plan_output(plan: RetryPlan) -> dict[str, object]:
    return {
        "plan_id": plan.plan_id,
        "direction": plan.direction,
        "candidates": [candidate_output(item) for item in plan.candidates],
        "task_instances": [
            {
                "region": item.region.value,
                "dag_id": item.dag_id,
                "run_id": item.run_id,
                "task_id": item.task_id,
                "state": item.state,
            }
            for item in plan.task_instances
        ],
        "approval_required": True,
    }
