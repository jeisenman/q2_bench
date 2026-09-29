"""Workflow-harness adapter for deterministic production support."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from domain import AgentDefinition
from workflow_harness import (
    SideEffectPolicy,
    WorkflowCapabilityDefinition,
    WorkflowDefinition,
    WorkflowExecutionContext,
    WorkflowRequest,
    WorkflowStageDefinition,
)
from workspaces.data_engineering.workflows.prod_support.models import (
    ProdSupportOutcome,
)
from workspaces.data_engineering.workflows.prod_support.reporting_config import (
    ProdSupportReportConfig,
)


class ProdSupportInvestigator(Protocol):
    """Expose the existing production-support investigation boundary."""

    @property
    def definition(self) -> AgentDefinition:
        """Return the production-support agent definition."""
        ...

    async def investigate(
        self,
        prompt: str,
        *,
        report_config: ProdSupportReportConfig | None = None,
        correlation_id: str | None = None,
    ) -> ProdSupportOutcome:
        """Return a structured production-support outcome."""
        ...


@dataclass(frozen=True, slots=True)
class ProdSupportWorkflowInput:
    """Provide validated input to the production-support harness adapter."""

    prompt: str
    report_config: ProdSupportReportConfig

    def __post_init__(self) -> None:
        """Reject empty production-support prompts."""
        if not self.prompt.strip():
            message = "production-support prompt must not be empty"
            raise ValueError(message)


class ProductionSupportHarnessWorkflow:
    """Run the existing production-support workflow through shared contracts."""

    def __init__(self, investigator: ProdSupportInvestigator) -> None:
        """Initialize with the existing deterministic investigator."""
        self._investigator = investigator
        agent_definition = investigator.definition
        self._definition = WorkflowDefinition(
            name="production-support",
            description=(
                "Discover, triage, and report scoped data-engineering "
                "production failures."
            ),
            version=agent_definition.version,
            capabilities=(
                WorkflowCapabilityDefinition(
                    name="airflow.read",
                    description="Read Airflow task instances and exact task logs.",
                ),
                WorkflowCapabilityDefinition(
                    name="cluster.read",
                    description="Read regional cluster health evidence.",
                ),
                WorkflowCapabilityDefinition(
                    name="resource-discovery.read",
                    description="Resolve client identities and environments.",
                ),
                WorkflowCapabilityDefinition(
                    name="oms.read",
                    description="Read bounded OMS evidence when required.",
                ),
            ),
            stages=(
                WorkflowStageDefinition(
                    name="investigate",
                    description=(
                        "Discover, resolve, triage, and render the authoritative "
                        "read-only report."
                    ),
                    capabilities=(
                        "airflow.read",
                        "cluster.read",
                        "resource-discovery.read",
                        "oms.read",
                    ),
                    side_effect_policy=SideEffectPolicy.READ_ONLY,
                ),
            ),
        )

    @property
    def definition(self) -> WorkflowDefinition:
        """Return immutable production-support workflow metadata."""
        return self._definition

    @property
    def agent_definition(self) -> AgentDefinition:
        """Return the existing public agent definition for MCP compatibility."""
        return self._investigator.definition

    async def execute(
        self,
        request: WorkflowRequest[ProdSupportWorkflowInput],
        context: WorkflowExecutionContext,
    ) -> ProdSupportOutcome:
        """Execute production support as one read-only harness stage."""

        async def investigate() -> ProdSupportOutcome:
            workflow_input = request.input
            return await self._investigator.investigate(
                workflow_input.prompt,
                report_config=workflow_input.report_config,
                correlation_id=request.correlation_id,
            )

        return await context.run_stage("investigate", investigate)
