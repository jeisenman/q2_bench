"""Tests for production-support durable memory boundaries."""

import asyncio
from datetime import UTC, datetime

from adapters.local import InMemoryAgentMemoryStore
from agent_memory import AgentMemory, MemoryKind, MemoryScope, MemoryScopeType
from workspaces.data_engineering.agents.production_support import (
    AirflowFailure,
    InvestigationServices,
    ProductionSupportWorkflow,
)
from workspaces.data_engineering.agents.production_support.models import Region


class ExactLogAirflow:
    """Return one exact task log for deterministic memory tests."""

    def __init__(self, failure: AirflowFailure, exact_log: str) -> None:
        self.failure = failure
        self.exact_log = exact_log

    async def discover_failures(
        self,
        since: datetime,
    ) -> tuple[AirflowFailure, ...]:
        del since
        return (self.failure,)

    async def fetch_log(self, failure: AirflowFailure) -> str:
        assert failure == self.failure
        return self.exact_log


def test_agent_persists_bounded_diagnosis_summaries() -> None:
    failure = AirflowFailure(
        region=Region.US_01,
        dag_id="example-dag",
        run_id="run-24",
        task_id="example-task",
        start_at=datetime(2026, 9, 24, 5, tzinfo=UTC),
        end_at=datetime(2026, 9, 24, 6, tzinfo=UTC),
    )
    memory = AgentMemory(
        InMemoryAgentMemoryStore(),
        agent_id="production-support",
        scope=MemoryScope(
            tenant_id="q2",
            scope_type=MemoryScopeType.TEAM,
            scope_id="data-engineering",
        ),
    )
    exact_log = "secret diagnostic context\nOOMKilled terminal evidence"
    agent = ProductionSupportWorkflow(
        ExactLogAirflow(failure, exact_log),
        clock=lambda: datetime(2026, 9, 25, 12, tzinfo=UTC),
        investigation=InvestigationServices(memory=memory),
    )

    outcome = asyncio.run(agent.investigate("do today's prod support"))

    assert len(outcome.memory_summaries) == 1
    summary = outcome.memory_summaries[0]
    assert summary.kind is MemoryKind.SUMMARY
    assert summary.agent_id == "production-support"
    assert "confirmed_oom" in summary.content
    assert exact_log not in summary.content
    assert "secret diagnostic context" not in str(summary.metadata)
