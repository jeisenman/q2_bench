"""Tests for MCP follow-up retry serialization and approval checks."""

from __future__ import annotations

import asyncio

import pytest

from mcp_servers import prod_support_follow_up
from workspaces.data_engineering.agents.prod_support import (
    Region,
    RetryCandidate,
    RetryPlan,
)
from workspaces.data_engineering.agents.prod_support.retry_models import (
    RetryBatch,
    RetryTaskReference,
)


def _candidate() -> dict[str, object]:
    return {
        "number": 1,
        "region": "CA-02",
        "dag_id": "dag",
        "run_id": "run",
        "task_id": "task",
        "label": "job",
    }


class FakeFollowUpAgent:
    """Return a fixed dry run and state read-back."""

    async def plan(
        self,
        direction: str,
        candidates: tuple[RetryCandidate, ...],
    ) -> RetryPlan:
        batch = RetryBatch(Region.CA_02, "dag", "run", ("task",))
        return RetryPlan(
            "plan-1",
            direction,
            candidates,
            (batch,),
            (RetryTaskReference(Region.CA_02, "dag", "run", "task", "failed"),),
        )

    async def execute(
        self,
        plan: RetryPlan,
        approval_id: str,
    ) -> tuple[RetryTaskReference, ...]:
        del plan, approval_id
        return (RetryTaskReference(Region.CA_02, "dag", "run", "task", "queued"),)


def test_follow_up_tools_plan_and_execute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        prod_support_follow_up,
        "_follow_up_agent",
        FakeFollowUpAgent,
    )

    planned = asyncio.run(
        prod_support_follow_up.plan_prod_support_follow_up(
            "retry CA",
            [_candidate()],
        )
    )
    executed = asyncio.run(
        prod_support_follow_up.execute_prod_support_follow_up(
            "retry CA",
            [_candidate()],
            "plan-1",
            "approval-1",
        )
    )

    assert planned["approval_required"] is True
    assert planned["task_instances"][0]["region"] == "CA-02"
    assert executed["task_instances"][0]["state"] == "queued"


def test_follow_up_tool_rejects_changed_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        prod_support_follow_up,
        "_follow_up_agent",
        FakeFollowUpAgent,
    )

    with pytest.raises(ValueError, match="does not match"):
        asyncio.run(
            prod_support_follow_up.execute_prod_support_follow_up(
                "retry CA",
                [_candidate()],
                "old-plan",
                "approval-1",
            )
        )


def test_follow_up_tool_rejects_invalid_candidate() -> None:
    with pytest.raises(ValueError, match="invalid"):
        prod_support_follow_up.candidate_input({"number": "one"})
