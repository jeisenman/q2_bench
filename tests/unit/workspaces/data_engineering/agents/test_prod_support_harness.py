from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

from domain import AgentDefinition
from workflow_harness import InMemoryWorkflowRecorder, WorkflowRequest, WorkflowRunner
from workspaces.data_engineering.workflows.prod_support import (
    ProdSupportOutcome,
    ProdSupportReportConfig,
    ProdSupportWorkflowInput,
    ProductionSupportHarnessWorkflow,
    Region,
)


class FakeInvestigator:
    definition = AgentDefinition(
        name="prod-support",
        description="Investigate production failures.",
        instructions="Investigate.",
        version="7",
    )

    def __init__(self, outcome: ProdSupportOutcome) -> None:
        self.outcome = outcome
        self.calls: list[tuple[str, ProdSupportReportConfig | None, str | None]] = []

    async def investigate(
        self,
        prompt: str,
        *,
        report_config: ProdSupportReportConfig | None = None,
        correlation_id: str | None = None,
    ) -> ProdSupportOutcome:
        self.calls.append((prompt, report_config, correlation_id))
        return self.outcome


def test_prod_support_adapter_runs_existing_investigator() -> None:
    outcome = ProdSupportOutcome(
        operational_date=date(2026, 9, 27),
        failed_since=datetime(2026, 9, 27, 5, tzinfo=UTC),
        failures=(),
        diagnoses=(),
        report="report",
        developer_report="developer",
        data_internal_report="internal",
        follow_up="follow up",
        resource_discovery_results=(),
        regions=(Region.US_01, Region.CA_02),
        retry_candidates=(),
        memory_summaries=(),
    )
    investigator = FakeInvestigator(outcome)
    workflow = ProductionSupportHarnessWorkflow(investigator)
    recorder = InMemoryWorkflowRecorder()
    config = ProdSupportReportConfig()

    result = asyncio.run(
        WorkflowRunner(recorder).run(
            workflow,
            WorkflowRequest(
                input=ProdSupportWorkflowInput(
                    prompt="Do prod support.",
                    report_config=config,
                ),
                correlation_id="support-1",
            ),
        )
    )

    assert result.output is outcome
    assert result.completed_stages == ("investigate",)
    assert investigator.calls == [("Do prod support.", config, "support-1")]
    assert workflow.definition.version == "7"
    assert workflow.agent_definition is investigator.definition
