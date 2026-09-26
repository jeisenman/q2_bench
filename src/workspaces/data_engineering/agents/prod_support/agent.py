"""Production-support agent orchestrator."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import TypeVar

from domain import AgentDefinition, AgentRequest, AgentResult
from workspaces.data_engineering.agents.prod_support.airflow_checker import (
    AirflowChecker,
)
from workspaces.data_engineering.agents.prod_support.cluster_checker import (
    ClusterChecker,
)
from workspaces.data_engineering.agents.prod_support.dates import (
    resolve_query_window,
)
from workspaces.data_engineering.agents.prod_support.investigation import (
    FailureInvestigator,
    InvestigationServices,
)
from workspaces.data_engineering.agents.prod_support.models import (
    AirflowFailure,
    ProdSupportOutcome,
)
from workspaces.data_engineering.agents.prod_support.ports import (
    AirflowFailureSource,
    ClusterHealthSource,
    ResourceDiscoveryInvoker,
)
from workspaces.data_engineering.agents.prod_support.reporting import (
    ProdSupportReportContext,
    format_reports_with_context,
)
from workspaces.data_engineering.agents.prod_support.reporting_config import (
    ProdSupportReportConfig,
)
from workspaces.data_engineering.agents.prod_support.reporting_details import (
    client_id as extract_client_id,
)
from workspaces.data_engineering.agents.prod_support.tools import (
    CLASSIFY_FAILURE,
    DISCOVER_FAILURES,
    FETCH_TASK_LOG,
    INSPECT_WORKLOAD,
    QUERY_OMS_JOB,
    TRIGGER_RESOURCE_DISCOVERY,
)

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")
PROD_SUPPORT_DEFINITION = AgentDefinition(
    name="prod-support",
    description="Discover and diagnose production Airflow failures.",
    instructions=(
        "Run the deterministic replay workflow before repository exploration. "
        "Resolve dates from the request, parse every relevant Airflow record "
        "programmatically, and cite exact task-log evidence. Resolve every client "
        "identifier in DAG or task IDs through Resource Discovery before triage or "
        "reporting. Investigate US and "
        "CA concurrently. Assign parallel workers by operational capability, not "
        "arbitrary record ranges. Use Airflow for batch evidence and query OMS only "
        "with exact identifiers when corroboration is required. For Spark workloads, "
        "start exact Airflow and OMS evidence queries concurrently; cancel pending "
        "OMS work when Airflow proves AirflowTaskTimeout. Diagnose "
        "independently before reading curated expectations. Keep tool output "
        "targeted. Build OMS queries from parameterized client, run, task, "
        "attempt, and the task's full UTC calendar day. Inspect the Airflow "
        "operator before routing evidence: query regional DI_Scheduling_CL "
        "only for confirmed Spark workloads. Page backward through the same DAG "
        "and task when the latest log is unavailable or non-diagnostic. Report "
        "bounded Airflow links, US and CA KEDA and pod health, resource-discovered "
        "resend applications, per-client dates and counts, large-resend escalation "
        "for both audiences, and channel-specific omission policy. "
        "Trigger the Resource Discovery agent for every unique client-scoped "
        "failure before triage; preserve unresolved and ambiguous results. "
        "Never mix US and CA findings in the same regional section. Reject a final "
        "report when a regional finding appears under the other region or when a "
        "cluster is described as both healthy and unhealthy from the same evidence. "
        "Group clients that fail on the same job into one report line, and group "
        "multiple jobs for the same client into one concise client line. Fetch the "
        "exact task log even when "
        "discovery includes a non-empty log excerpt. Classify the full log, then "
        "retain only source, status, original character count, and at most three "
        "diagnostic lines; never return raw log bodies. Follow-ups must contain "
        "only actionable resend or approval-gated rerun choices with dates. "
        "Treat validate_event_bus_opportunities as missing-snapshot validation; "
        "do not repeat that implication as a verbose diagnosis in Data Internal. "
        "Prefer explicit timeout, OOM, and distinctness-validation evidence when "
        "available. Apply typed Data Internal omission groups, omit those jobs from "
        "rerun follow-ups, escalate resends above 100 events to pd-rix, and link "
        "failures over five attempts to the KPO sizing agent interface. "
        "Data Internal must contain no periods. Treat exit code -9 as an unknown "
        "resource termination unless exact Airflow or OMS evidence corroborates "
        "memory pressure. Derive cluster status only from primary application, pod, "
        "and DAG checks; keep access gaps and retired replicas as warnings. "
        "Run the repository quality check when changing code, and "
        "never mutate production systems."
    ),
    tools=(
        DISCOVER_FAILURES,
        FETCH_TASK_LOG,
        INSPECT_WORKLOAD,
        QUERY_OMS_JOB,
        CLASSIFY_FAILURE,
        TRIGGER_RESOURCE_DISCOVERY,
    ),
    version="11",
)


class ProdSupportAgent:
    """Discover, classify, and report Airflow failures."""

    def __init__(
        self,
        source: AirflowFailureSource,
        *,
        clock: Callable[[], datetime] | None = None,
        resource_discovery: ResourceDiscoveryInvoker | None = None,
        cluster_health: ClusterHealthSource | None = None,
        investigation: InvestigationServices | None = None,
    ) -> None:
        """Initialize with either a production or replay Airflow source."""
        services = investigation or InvestigationServices()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._resource_discovery = resource_discovery
        self._airflow_checker = AirflowChecker(source)
        self._cluster_checker = ClusterChecker(cluster_health)
        self._max_parallel = services.max_parallel
        self._failure_investigator = FailureInvestigator(
            source,
            prior_logs=services.prior_logs,
            task_metadata=services.task_metadata,
            oms=services.oms,
        )

    @property
    def definition(self) -> AgentDefinition:
        """Return the production-support definition."""
        return PROD_SUPPORT_DEFINITION

    async def run(self, request: AgentRequest) -> AgentResult:
        """Execute the read-only production-support workflow."""
        outcome = await self.investigate(request.prompt)
        return AgentResult(
            output=outcome.report,
            correlation_id=request.correlation_id,
            tool_calls=tuple(tool.name for tool in self.definition.tools),
            attributes=(
                ("operational_date", outcome.operational_date.isoformat()),
                ("failed_since", outcome.failed_since.isoformat()),
                ("failure_count", len(outcome.failures)),
                (
                    "resource_discovery_count",
                    len(outcome.resource_discovery_results),
                ),
                (
                    "evidence_characters_read",
                    sum(item.original_char_count for item in outcome.diagnoses),
                ),
                (
                    "evidence_characters_retained",
                    sum(len(item.log) for item in outcome.failures),
                ),
            ),
        )

    async def investigate(
        self,
        prompt: str,
        *,
        report_config: ProdSupportReportConfig | None = None,
    ) -> ProdSupportOutcome:
        """Return structured evidence and reporting for benchmark evaluation."""
        reference_time = self._clock()
        window = resolve_query_window(prompt, reference_time)
        failed_before = window.failed_since + timedelta(days=1)
        failures, cluster_health = await asyncio.gather(
            self._airflow_checker.check(window.failed_since, failed_before),
            self._cluster_checker.check(),
        )
        resource_results = await self._trigger_resource_discovery(failures)
        reportable = tuple(
            failure
            for failure in failures
            if not _ignored_by_resource_discovery(failure, resource_results)
        )
        investigated = await self._bounded_map(
            reportable,
            self._failure_investigator.investigate,
        )
        hydrated = tuple(item[0] for item in investigated)
        diagnoses = tuple(item[1] for item in investigated)
        reports = format_reports_with_context(
            window.operational_date,
            hydrated,
            diagnoses,
            context=ProdSupportReportContext(
                resource_discovery_results=resource_results,
                config=report_config or ProdSupportReportConfig(),
                cluster_health=cluster_health,
            ),
        )
        return ProdSupportOutcome(
            operational_date=window.operational_date,
            failed_since=window.failed_since,
            failures=hydrated,
            diagnoses=diagnoses,
            report=reports.combined,
            developer_report=reports.developer,
            data_internal_report=reports.data_internal,
            follow_up=reports.follow_up,
            resource_discovery_results=resource_results,
        )

    async def _trigger_resource_discovery(
        self,
        failures: tuple[AirflowFailure, ...],
    ) -> tuple[AgentResult, ...]:
        """Resolve every unique client-scoped failure through the injected agent."""
        if self._resource_discovery is None:
            return ()
        client_ids = tuple(
            sorted(
                {
                    client_id
                    for failure in failures
                    if (client_id := extract_client_id(failure)) is not None
                }
            )
        )
        requests = tuple(
            AgentRequest(
                prompt=f"Resolve production resources for client {client_id}.",
                correlation_id=f"prod-support-resource-{client_id}",
                attributes=(
                    ("identifier_kind", "client_id"),
                    ("identifier_value", client_id),
                ),
            )
            for client_id in client_ids
        )
        return tuple(await self._bounded_map(requests, self._resource_discovery.run))

    async def _bounded_map(
        self,
        values: tuple[InputT, ...],
        operation: Callable[[InputT], Awaitable[OutputT]],
    ) -> tuple[OutputT, ...]:
        """Run an async operation with repository-safe worker parallelism."""
        semaphore = asyncio.Semaphore(self._max_parallel)

        async def invoke(value: InputT) -> OutputT:
            async with semaphore:
                result = operation(value)
                return await result

        return tuple(await asyncio.gather(*(invoke(value) for value in values)))


def _ignored_by_resource_discovery(
    failure: AirflowFailure,
    results: tuple[AgentResult, ...],
) -> bool:
    """Apply an explicit Resource Discovery support-ignore marker."""
    identifier = extract_client_id(failure)
    return any(
        dict(result.attributes).get("identifier_value") == identifier
        and dict(result.attributes).get("prod_support_ignore") is True
        for result in results
    )
