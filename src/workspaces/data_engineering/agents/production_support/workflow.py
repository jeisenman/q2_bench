"""Deterministic tool workflow behind the production-support agent suite."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TypeVar

from agent_memory import MemoryRecord
from domain import AgentDefinition, AgentRequest, AgentResult
from observability import traced_agent_run, traced_operation
from workspaces.data_engineering.agents.production_support.cluster_checker import (
    ClusterChecker,
)
from workspaces.data_engineering.agents.production_support.dates import (
    resolve_query_window,
)
from workspaces.data_engineering.agents.production_support.failure_tools import (
    FailureDiscoveryTool,
)
from workspaces.data_engineering.agents.production_support.investigation import (
    FailureInvestigator,
    InvestigationServices,
)
from workspaces.data_engineering.agents.production_support.models import (
    AirflowFailure,
    FailureDiagnosis,
    FailureKind,
    ProdSupportOutcome,
)
from workspaces.data_engineering.agents.production_support.ports import (
    AirflowFailureSource,
    AirflowSuccessSource,
    ClusterHealthSource,
    ResourceDiscoveryInvoker,
)
from workspaces.data_engineering.agents.production_support.report_agents import (
    ReportingAgent,
)
from workspaces.data_engineering.agents.production_support.report_findings import (
    ReportFindings,
)
from workspaces.data_engineering.agents.production_support.reporting import (
    ProdSupportReportContext,
    format_reports_with_context,
)
from workspaces.data_engineering.agents.production_support.reporting_config import (
    ProdSupportReportConfig,
)
from workspaces.data_engineering.agents.production_support.reporting_details import (
    client_id as extract_client_id,
)
from workspaces.data_engineering.agents.production_support.retry_agent import (
    retry_candidates,
)
from workspaces.data_engineering.agents.production_support.scope import resolve_scope
from workspaces.data_engineering.agents.production_support.suite import (
    build_production_support_suite,
)
from workspaces.data_engineering.agents.production_support.triage_manager import (
    TriageManager,
)

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class ProductionSupportWorkflow:
    """Execute production-support tools without defining a second agent."""

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
        self._source = source
        self._clock = clock or (lambda: datetime.now(UTC))
        self._resource_discovery = resource_discovery
        self._failure_discovery = FailureDiscoveryTool(source)
        self._cluster_checker = ClusterChecker(cluster_health)
        self._report_runtime = services.report_runtime
        self._memory = services.memory
        self._max_parallel = services.max_parallel
        self._triage_manager = TriageManager(
            FailureInvestigator(
                source,
                prior_logs=services.prior_logs,
                task_metadata=services.task_metadata,
                oms=services.oms,
            ),
            max_parallel=services.max_parallel,
        )

    @property
    def definition(self) -> AgentDefinition:
        """Return the sole public production-support orchestrator definition."""
        return build_production_support_suite().orchestrator

    @traced_agent_run
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
                ("memory_summary_count", len(outcome.memory_summaries)),
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
        async with traced_operation(
            "agent.prod-support.investigate",
            attributes={
                "q2.agent.name": self.definition.name,
                "q2.agent.correlation_id": correlation_id or "generated",
            },
        ):
            return await self._investigate(
                prompt,
                report_config=report_config,
                correlation_id=correlation_id,
            )

    async def _investigate(
        self,
        prompt: str,
        *,
        report_config: ProdSupportReportConfig | None,
        correlation_id: str | None,
    ) -> ProdSupportOutcome:
        """Execute the structured investigation inside its trace boundary."""
        reference_time = self._clock()
        window = resolve_query_window(prompt, reference_time)
        scope = resolve_scope(prompt)
        config = report_config or ProdSupportReportConfig()
        failed_before = window.failed_since + timedelta(days=1)
        failures, cluster_health = await asyncio.gather(
            self._failure_discovery.discover(
                window.failed_since,
                failed_before,
                scope.regions,
            ),
            self._cluster_checker.check(
                scope.regions,
                restart_window_start=window.failed_since,
                restart_window_end=failed_before,
            ),
        )
        identity_failures = tuple(
            failure
            for failure in failures
            if config.configured_omission_group(failure) is None
        )
        resource_results = await self._trigger_resource_discovery(identity_failures)
        reportable = tuple(
            failure
            for failure in failures
            if not _ignored_by_resource_discovery(failure, resource_results)
        )
        investigated = await self._triage_manager.triage(reportable)
        investigated_by_id = {item[0].failure_id: item for item in investigated}
        recovered_omissions = await self._verified_omission_ids(
            reportable,
            config,
            window.failed_since,
            failed_before,
        )
        verified_config = config.with_verified_omissions(recovered_omissions)
        hydrated = tuple(
            investigated_by_id[failure.failure_id][0] for failure in reportable
        )
        diagnoses = tuple(
            (
                _omitted_diagnosis(
                    failure,
                    verified_config,
                    investigated_by_id[failure.failure_id][1],
                )
                if verified_config.omits(failure)
                else investigated_by_id[failure.failure_id][1]
            )
            for failure in reportable
        )
        report_context = ProdSupportReportContext(
            resource_discovery_results=resource_results,
            config=verified_config,
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
        memory_summaries = await self._remember_diagnoses(hydrated, diagnoses)
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
            retry_candidates=retry_candidates(findings),
            memory_summaries=memory_summaries,
        )

    async def _remember_diagnoses(
        self,
        failures: tuple[AirflowFailure, ...],
        diagnoses: tuple[FailureDiagnosis, ...],
    ) -> tuple[MemoryRecord, ...]:
        """Persist bounded summaries without retaining logs or report content."""
        memory = self._memory
        if memory is None:
            return ()
        failure_by_id = {failure.failure_id: failure for failure in failures}

        async def remember(diagnosis: FailureDiagnosis) -> MemoryRecord:
            failure = failure_by_id[diagnosis.failure_id]
            return await memory.remember_summary(
                key=(
                    f"{diagnosis.failure_id}:{diagnosis.kind.value}:"
                    f"{diagnosis.source.value}:{diagnosis.status.value}"
                ),
                content=(
                    f"{failure.region.value} {failure.dag_id} "
                    f"{failure.task_id}: {diagnosis.kind.value}"
                ),
                metadata=(
                    ("region", failure.region.value),
                    ("dag_id", failure.dag_id),
                    ("task_id", failure.task_id),
                    ("diagnosis", diagnosis.kind.value),
                    ("confidence", diagnosis.confidence),
                    ("evidence_source", diagnosis.source.value),
                    ("evidence_status", diagnosis.status.value),
                ),
            )

        return await self._bounded_map(diagnoses, remember)

    async def _verified_omission_ids(
        self,
        failures: tuple[AirflowFailure, ...],
        config: ProdSupportReportConfig,
        start_at: datetime,
        end_at: datetime,
    ) -> tuple[str, ...]:
        """Return omission candidates with a bounded same-task success."""
        source = self._source
        if not isinstance(source, AirflowSuccessSource):
            return ()
        candidates = tuple(filter(config.configured_omission_group, failures))

        async def verify(failure: AirflowFailure) -> str | None:
            recovered = await source.has_success_within(
                failure,
                start_at,
                end_at,
            )
            return failure.failure_id if recovered else None

        results = await self._bounded_map(candidates, verify)
        return tuple(item for item in results if item is not None)

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
    diagnosis: FailureDiagnosis,
) -> FailureDiagnosis:
    """Return a recovered omission while retaining exact-log provenance."""
    group = config.omission_group(failure)
    label = group.value.upper() if group is not None else "configured"
    return replace(
        diagnosis,
        kind=FailureKind.OMITTED,
        confidence="verified_recovery",
        evidence=(
            f"{label} exact failure log reviewed",
            "same DAG and task succeeded inside the operational window",
            *diagnosis.evidence,
        )[:3],
    )
