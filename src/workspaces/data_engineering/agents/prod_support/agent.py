"""Production-support agent orchestrator."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace
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
    EvidenceSource,
    EvidenceStatus,
    FailureDiagnosis,
    FailureKind,
    ProdSupportOutcome,
)
from workspaces.data_engineering.agents.prod_support.ports import (
    AirflowFailureSource,
    ClusterHealthSource,
    ResourceDiscoveryInvoker,
)
from workspaces.data_engineering.agents.prod_support.report_agents import (
    ReportingAgent,
)
from workspaces.data_engineering.agents.prod_support.report_findings import (
    ReportFindings,
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
from workspaces.data_engineering.agents.prod_support.scope import resolve_scope
from workspaces.data_engineering.agents.prod_support.templates import (
    PROD_SUPPORT_REPORT_TEMPLATE,
)
from workspaces.data_engineering.agents.prod_support.tools import (
    CLASSIFY_FAILURE,
    DISCOVER_FAILURES,
    FETCH_TASK_LOG,
    INSPECT_CLUSTER_HEALTH,
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
        "Accept 'Do prod support', 'Do US prod support', or 'Do CA prod support', "
        "with an optional date. Default to the previous operational day and both "
        "regions. Run the selected cluster-health and Airflow checks concurrently, "
        "then pass their validated results to one reporting agent. Cluster checks "
        "return pod state, restart counts, and KEDA health. Airflow checks return "
        "direct errors and do not triage configured D2P or MI3 omissions. No component "
        "may delegate further or mutate production."
    ),
    tools=(
        INSPECT_CLUSTER_HEALTH,
        DISCOVER_FAILURES,
        FETCH_TASK_LOG,
        INSPECT_WORKLOAD,
        QUERY_OMS_JOB,
        CLASSIFY_FAILURE,
        TRIGGER_RESOURCE_DISCOVERY,
    ),
    version="15",
    output_template=PROD_SUPPORT_REPORT_TEMPLATE,
    can_delegate=True,
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
        self._report_runtime = services.report_runtime
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
        outcome = await self.investigate(
            request.prompt,
            correlation_id=request.correlation_id,
        )
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
                ("regions", ",".join(region.value for region in outcome.regions)),
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
        correlation_id: str | None = None,
    ) -> ProdSupportOutcome:
        """Return structured evidence and reporting for benchmark evaluation."""
        reference_time = self._clock()
        window = resolve_query_window(prompt, reference_time)
        scope = resolve_scope(prompt)
        config = report_config or ProdSupportReportConfig()
        failed_before = window.failed_since + timedelta(days=1)
        failures, cluster_health = await asyncio.gather(
            self._airflow_checker.check(
                window.failed_since,
                failed_before,
                regions=scope.regions,
            ),
            self._cluster_checker.check(scope.regions),
        )
        resource_results = await self._trigger_resource_discovery(failures)
        reportable = tuple(
            failure
            for failure in failures
            if not _ignored_by_resource_discovery(failure, resource_results)
        )
        investigation_targets = tuple(
            failure
            for failure in reportable
            if not config.skips_airflow_triage(failure)
        )
        investigated = await self._bounded_map(
            investigation_targets,
            self._failure_investigator.investigate,
        )
        investigated_by_id = {item[0].failure_id: item for item in investigated}
        hydrated: tuple[AirflowFailure, ...] = tuple(
            (
                replace(failure, log="")
                if config.skips_airflow_triage(failure)
                else investigated_by_id[failure.failure_id][0]
            )
            for failure in reportable
        )
        diagnoses = tuple(
            (
                _omitted_diagnosis(failure, config)
                if config.skips_airflow_triage(failure)
                else investigated_by_id[failure.failure_id][1]
            )
            for failure in reportable
        )
        report_context = ProdSupportReportContext(
            resource_discovery_results=resource_results,
            config=config,
            cluster_health=cluster_health,
            regions=scope.regions,
        )
        reports = format_reports_with_context(
            window.operational_date,
            hydrated,
            diagnoses,
            context=report_context,
        )
        findings = ReportFindings(
            failures=hydrated,
            diagnoses=diagnoses,
            resource_discovery_results=resource_results,
            config=report_context.config,
            cluster_health=cluster_health,
            regions=scope.regions,
        )
        if self._report_runtime is not None:
            reports = await ReportingAgent(self._report_runtime).write(
                window.operational_date,
                findings,
                reports,
                correlation_id=(
                    correlation_id
                    or f"prod-support:{window.operational_date.isoformat()}"
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
            regions=scope.regions,
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


def _omitted_diagnosis(
    failure: AirflowFailure,
    config: ProdSupportReportConfig,
) -> FailureDiagnosis:
    """Return the registered no-triage diagnosis for D2P or MI3."""
    group = config.omission_group(failure)
    label = group.value.upper() if group is not None else "configured"
    return FailureDiagnosis(
        failure_id=failure.failure_id,
        kind=FailureKind.OMITTED,
        confidence="configured",
        evidence=(f"{label} triage omitted by policy",),
        source=EvidenceSource.UNKNOWN,
        status=EvidenceStatus.UNKNOWN,
    )
