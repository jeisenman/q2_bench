"""Tests for direct MCP follow-up retry execution."""

from __future__ import annotations

import asyncio

import pytest

from mcp_servers import prod_support_follow_up
from workspaces.data_engineering.workflows.prod_support import (
    Region,
    RetryCandidate,
)
from workspaces.data_engineering.workflows.prod_support.retry_models import (
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


US_URL = "https://airflow-us01.example/failed"
CA_URL = "https://airflow-ca02.example/failed"


class FakeFollowUpAgent:
    """Return a fixed retry state read-back."""

    async def execute(
        self,
        direction: str,
        candidates: tuple[RetryCandidate, ...],
    ) -> tuple[RetryTaskReference, ...]:
        del direction, candidates
        return (RetryTaskReference(Region.CA_02, "dag", "run", "task", "queued"),)


def test_follow_up_tool_executes_and_returns_validation_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        prod_support_follow_up,
        "_follow_up_agent",
        FakeFollowUpAgent,
    )

    executed = asyncio.run(
        prod_support_follow_up.execute_prod_support_follow_up(
            "retry CA",
            [_candidate()],
            [US_URL, CA_URL],
        )
    )

    assert executed["task_instances"][0]["state"] == "queued"
    assert executed["links"] == (US_URL, CA_URL)
    assert executed["validation_urls"] == (US_URL, CA_URL)


def test_follow_up_tool_returns_debug_trace_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("Q2_MCP_DEBUG", "1")
    monkeypatch.setattr(
        prod_support_follow_up,
        "_follow_up_agent",
        FakeFollowUpAgent,
    )

    executed = asyncio.run(
        prod_support_follow_up.execute_prod_support_follow_up(
            "retry CA",
            [_candidate()],
            [US_URL, CA_URL],
            correlation_id="follow-up-debug-1",
        )
    )

    debug_trace = executed["debug_trace"]
    assert debug_trace["correlation_id"] == "follow-up-debug-1"
    assert debug_trace["events"][-1]["event"] == "tool.complete"


def test_follow_up_tool_requires_both_validation_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        prod_support_follow_up,
        "_follow_up_agent",
        FakeFollowUpAgent,
    )

    with pytest.raises(ValueError, match="US and CA"):
        asyncio.run(
            prod_support_follow_up.execute_prod_support_follow_up(
                "retry CA",
                [_candidate()],
                [CA_URL],
            )
        )


def test_follow_up_tool_rejects_invalid_candidate() -> None:
    with pytest.raises(ValueError, match="invalid"):
        prod_support_follow_up.candidate_input({"number": "one"})
