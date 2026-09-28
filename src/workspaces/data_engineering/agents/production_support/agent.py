"""Production Support Agent facade used by the MCP composition root."""

from domain import AgentDefinition, AgentRequest, AgentResult, ToolDefinition
from workspaces.data_engineering.agents.production_support.client_investigation import (
    ClientFailureWorkflow,
)
from workspaces.data_engineering.agents.production_support.instruction_loader import (
    load_instruction,
)
from workspaces.data_engineering.agents.production_support.models import (
    ProdSupportOutcome,
)
from workspaces.data_engineering.agents.production_support.reporting_config import (
    ProdSupportReportConfig,
)
from workspaces.data_engineering.agents.production_support.tools import (
    DISCOVER_FAILURES,
    FETCH_TASK_LOG,
    INSPECT_CLUSTER_HEALTH,
    RUN_PROD_SUPPORT_MCP,
)
from workspaces.data_engineering.agents.production_support.workflow import (
    ProductionSupportWorkflow,
)

PRODUCTION_SUPPORT_AGENT_DEFINITION = AgentDefinition(
    name="ProductionSupportAgent",
    description=(
        "Coordinate production resource discovery, failure evidence, "
        "classification, reporting, and approval-gated retries."
    ),
    instructions=load_instruction("production_support_agent"),
    tools=(
        RUN_PROD_SUPPORT_MCP,
        INSPECT_CLUSTER_HEALTH,
        DISCOVER_FAILURES,
        FETCH_TASK_LOG,
        ToolDefinition(
            "DelegateToResourceDiscoveryAgent",
            "Resolve one complete client UUID through Resource Discovery.",
        ),
        ToolDefinition(
            "DelegateToClassificationAgent",
            "Classify one exact failed task and map proven DV targets.",
        ),
        ToolDefinition(
            "DelegateToReporterAgent",
            "Render validated production-support findings.",
        ),
        ToolDefinition(
            "DelegateToApprovalGatedRetryAgent",
            "Plan or execute only explicitly approved exact retries.",
        ),
    ),
    version="1",
    can_delegate=True,
)


class ProductionSupportAgent:
    """Expose daily and client-scoped workflows through one agent boundary."""

    definition = PRODUCTION_SUPPORT_AGENT_DEFINITION

    def __init__(
        self,
        daily_workflow: ProductionSupportWorkflow,
        client_workflow: ClientFailureWorkflow,
    ) -> None:
        """Initialize with deterministic workflows and injected adapters."""
        self._daily = daily_workflow
        self._client = client_workflow

    async def run(self, request: AgentRequest) -> AgentResult:
        """Run the full daily production-support workflow."""
        outcome = await self.investigate(
            request.prompt,
            correlation_id=request.correlation_id,
        )
        return AgentResult(
            output=outcome.report,
            correlation_id=request.correlation_id,
            tool_calls=tuple(tool.name for tool in self.definition.tools),
        )

    async def investigate(
        self,
        prompt: str,
        *,
        report_config: ProdSupportReportConfig | None = None,
        correlation_id: str | None = None,
    ) -> ProdSupportOutcome:
        """Return structured daily production-support findings."""
        return await self._daily.investigate(
            prompt,
            report_config=report_config,
            correlation_id=correlation_id,
        )

    async def investigate_client_failures(
        self,
        client_guuid: str,
        since: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, object]:
        """Return a client-scoped failure diagnosis."""
        return await self._client.investigate_client_failures(
            client_guuid,
            since=since,
            correlation_id=correlation_id,
        )
