import asyncio
import json
from datetime import UTC, datetime

from domain import AgentDefinition, AgentRequest, AgentResult
from workspaces.data_engineering.agents.production_support import (
    AirflowFailure,
    InvestigationServices,
    ProductionSupportWorkflow,
)
from workspaces.data_engineering.agents.production_support.models import Region
from workspaces.data_engineering.agents.production_support.ports import (
    TaskLogUnavailableError,
)


class UnavailableLogAirflow:
    async def discover_failures(
        self,
        since: datetime,
    ) -> tuple[AirflowFailure, ...]:
        del since
        return (
            AirflowFailure(
                region=Region.US_01,
                dag_id="dag-24",
                run_id="run-24",
                task_id="task",
                start_at=datetime(2026, 9, 24, 5, tzinfo=UTC),
                end_at=datetime(2026, 9, 24, 6, tzinfo=UTC),
            ),
        )

    async def fetch_log(self, failure: AirflowFailure) -> str:
        raise TaskLogUnavailableError(failure.failure_id, 404)


class FakeReportRuntime:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run(
        self,
        definition: AgentDefinition,
        request: AgentRequest,
    ) -> AgentResult:
        self.calls.append(definition.name)
        payload = json.loads(request.prompt.partition("\n\n")[2])
        return AgentResult(
            output=json.dumps(
                {
                    "developer": (
                        "Message for developer:\n"
                        "  - US Cluster Health: healthy\n"
                        "  - CA Cluster Health: healthy"
                    ),
                    "data_internal": payload["deterministic_drafts"]["data_internal"],
                    "follow_up": payload["deterministic_drafts"]["follow_up"],
                }
            ),
            correlation_id=request.correlation_id,
        )


def test_agent_uses_one_reporting_call() -> None:
    runtime = FakeReportRuntime()
    agent = ProductionSupportWorkflow(
        UnavailableLogAirflow(),
        clock=lambda: datetime(2026, 9, 25, 12, tzinfo=UTC),
        investigation=InvestigationServices(report_runtime=runtime),
    )

    outcome = asyncio.run(agent.investigate("do prod support", correlation_id="case-1"))

    assert outcome.developer_report.endswith("CA Cluster Health: healthy")
    assert runtime.calls == ["prod-support.reporting"]
