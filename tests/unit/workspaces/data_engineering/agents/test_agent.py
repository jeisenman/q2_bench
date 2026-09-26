import asyncio
from datetime import UTC, datetime

import pytest

from domain import AgentRequest
from workspaces.data_engineering.agents.prod_support import (
    AirflowFailure,
    ProdSupportAgent,
)
from workspaces.data_engineering.agents.prod_support.models import Region
from workspaces.data_engineering.agents.prod_support.ports import (
    TaskLogUnavailableError,
)


class FakeAirflow:
    def __init__(self, failures: tuple[AirflowFailure, ...]) -> None:
        self.failures = failures

    async def discover_failures(self, since: datetime) -> tuple[AirflowFailure, ...]:
        del since
        return self.failures

    async def fetch_log(self, failure: AirflowFailure) -> str:
        return failure.log


class UnavailableLogAirflow(FakeAirflow):
    def __init__(
        self,
        failures: tuple[AirflowFailure, ...],
        status_code: int,
    ) -> None:
        super().__init__(failures)
        self.status_code = status_code

    async def fetch_log(self, failure: AirflowFailure) -> str:
        raise TaskLogUnavailableError(failure.failure_id, self.status_code)


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


def test_agent_definition_requires_operational_delivery_workflow() -> None:
    definition = ProdSupportAgent(FakeAirflow(())).definition

    assert (
        "Assign parallel workers by operational capability" in definition.instructions
    )
    assert "cancel pending OMS work" in definition.instructions
    assert "Page backward through the same DAG and task" in definition.instructions
    assert "US and CA KEDA and pod health" in definition.instructions
    assert definition.version == "5"


def test_agent_reports_missing_task_log_as_developer_evidence_gap() -> None:
    missing_log = failure(24, "")
    agent = ProdSupportAgent(
        UnavailableLogAirflow((missing_log,), 404),
        clock=lambda: datetime(2026, 9, 25, 12, tzinfo=UTC),
    )

    outcome = asyncio.run(agent.investigate("do today's prod support"))

    assert outcome.diagnoses[0].kind.value == "unknown"
    assert outcome.diagnoses[0].confidence == "evidence_gap"
    assert "Airflow task log unavailable: HTTP 404" in outcome.developer_report
    assert missing_log.dag_id in outcome.data_internal_report


def test_agent_still_fails_fast_for_non_404_log_errors() -> None:
    missing_log = failure(24, "")
    agent = ProdSupportAgent(
        UnavailableLogAirflow((missing_log,), 503),
        clock=lambda: datetime(2026, 9, 25, 12, tzinfo=UTC),
    )

    with pytest.raises(TaskLogUnavailableError, match="HTTP 503"):
        asyncio.run(agent.investigate("do today's prod support"))
