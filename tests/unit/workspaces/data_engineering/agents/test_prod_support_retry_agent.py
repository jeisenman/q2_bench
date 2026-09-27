"""Tests for production-support conversational retry planning."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from workspaces.data_engineering.agents.prod_support.models import (
    AirflowFailure,
    Region,
    RetryCandidate,
)
from workspaces.data_engineering.agents.prod_support.retry_agent import (
    FollowUpAgent,
    RetryDirectionError,
    retry_batches,
    select_retry_candidates,
)
from workspaces.data_engineering.agents.prod_support.retry_models import (
    RetryBatch,
    RetryTaskReference,
)

EXPECTED_REGIONAL_BATCHES = 2


def _candidate(number: int, region: Region) -> RetryCandidate:
    return RetryCandidate(
        number,
        region,
        f"dag-{number}",
        "run",
        f"task-{number}",
        f"job {number}",
    )


class FakeRetrySource:
    """Capture dry-run and execution requests."""

    def __init__(self) -> None:
        self.planned: list[RetryBatch] = []
        self.executed: list[tuple[RetryBatch, str]] = []

    async def plan_retry(
        self,
        batch: RetryBatch,
    ) -> tuple[RetryTaskReference, ...]:
        self.planned.append(batch)
        return tuple(
            RetryTaskReference(
                batch.region,
                batch.dag_id,
                batch.run_id,
                task_id,
                "failed",
            )
            for task_id in batch.task_ids
        )

    async def execute_retry(
        self,
        batch: RetryBatch,
        approval_id: str,
    ) -> tuple[RetryTaskReference, ...]:
        self.executed.append((batch, approval_id))
        return tuple(
            RetryTaskReference(
                batch.region,
                batch.dag_id,
                batch.run_id,
                task_id,
                "queued",
            )
            for task_id in batch.task_ids
        )


def test_selects_region_and_numbered_exclusions() -> None:
    candidates = (
        _candidate(1, Region.US_01),
        _candidate(2, Region.CA_02),
        _candidate(3, Region.CA_02),
        _candidate(4, Region.US_01),
    )

    assert select_retry_candidates("retry CA", candidates) == candidates[1:3]
    assert (
        select_retry_candidates(
            "retry jobs 1, 2, 3 but don't do 4",
            candidates,
        )
        == candidates[:3]
    )


def test_rejects_unknown_or_non_retry_direction() -> None:
    candidates = (_candidate(1, Region.US_01),)

    with pytest.raises(RetryDirectionError, match="unknown"):
        select_retry_candidates("retry jobs 2", candidates)
    with pytest.raises(RetryDirectionError, match="must request"):
        select_retry_candidates("inspect job 1", candidates)


def test_follow_up_agent_dry_runs_then_executes_approved_plan() -> None:
    source = FakeRetrySource()
    agent = FollowUpAgent(source)
    candidates = (
        _candidate(1, Region.US_01),
        _candidate(2, Region.CA_02),
    )

    plan = asyncio.run(agent.plan("retry all jobs", candidates))
    states = asyncio.run(agent.execute(plan, "approval-1"))

    assert plan.candidates == candidates
    assert retry_batches(candidates) == plan.batches
    assert len(source.planned) == EXPECTED_REGIONAL_BATCHES
    assert [item.state for item in states] == ["queued", "queued"]
    assert all(item[1] == "approval-1" for item in source.executed)


def test_follow_up_agent_requires_approval() -> None:
    source = FakeRetrySource()
    agent = FollowUpAgent(source)
    plan = asyncio.run(agent.plan("follow up", (_candidate(1, Region.US_01),)))

    with pytest.raises(RetryDirectionError, match="approval ID"):
        asyncio.run(agent.execute(plan, ""))


def test_retry_candidate_identity_is_region_bound() -> None:
    failure = AirflowFailure(
        Region.CA_02,
        "dag",
        "run",
        "task",
        datetime(2026, 9, 26, 5, tzinfo=UTC),
        datetime(2026, 9, 26, 6, tzinfo=UTC),
    )
    candidate = RetryCandidate(1, failure.region, "dag", "run", "task", "job")

    assert candidate.identity == "CA-02|dag|run|task"
