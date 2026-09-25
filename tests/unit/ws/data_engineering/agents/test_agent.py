import asyncio
from datetime import UTC, datetime

from agentsdk.domain import AgentRequest
from agentsdk.ws.data_engineering.agents.prod_support import (
    AirflowFailure,
    ProdSupportAgent,
)
from agentsdk.ws.data_engineering.agents.prod_support.models import Region


class FakeAirflow:
    def __init__(self, failures: tuple[AirflowFailure, ...]) -> None:
        self.failures = failures

    async def discover_failures(self, since: datetime) -> tuple[AirflowFailure, ...]:
        del since
        return self.failures

    async def fetch_log(self, failure: AirflowFailure) -> str:
        return failure.log


def failure(day: int, log: str) -> AirflowFailure:
    return AirflowFailure(
        region=Region.US_01,
        dag_id=f"dag-{day}",
        run_id=f"run-{day}",
        task_id="task",
        start_at=datetime(2026, 9, day, 5, tzinfo=UTC),
        end_at=datetime(2026, 9, day, 6, tzinfo=UTC),
        log=log,
    )


def test_agent_filters_prior_day_and_classifies_logs() -> None:
    agent = ProdSupportAgent(
        FakeAirflow(
            (
                failure(23, "old failure"),
                failure(24, "OOMKilled by container"),
            )
        ),
        clock=lambda: datetime(2026, 9, 25, 12, tzinfo=UTC),
    )

    outcome = asyncio.run(agent.investigate("do today's prod support"))

    assert [item.dag_id for item in outcome.failures] == ["dag-24"]
    assert outcome.diagnoses[0].kind.value == "confirmed_oom"
    assert "PROD SUPPORT 2026-09-24" in outcome.report


def test_agent_normalizes_framework_result() -> None:
    agent = ProdSupportAgent(
        FakeAirflow(()),
        clock=lambda: datetime(2026, 9, 25, 12, tzinfo=UTC),
    )

    result = asyncio.run(
        agent.run(AgentRequest("do prod support", correlation_id="case-1"))
    )

    assert result.correlation_id == "case-1"
    assert result.attributes[-1] == ("failure_count", 0)
