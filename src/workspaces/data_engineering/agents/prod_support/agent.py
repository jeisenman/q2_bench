"""Production-support agent orchestrator."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from domain import AgentDefinition, AgentRequest, AgentResult
from workspaces.data_engineering.agents.prod_support.classification import (
    classify_log,
)
from workspaces.data_engineering.agents.prod_support.dates import (
    resolve_query_window,
)
from workspaces.data_engineering.agents.prod_support.models import (
    AirflowFailure,
    FailureDiagnosis,
    FailureKind,
    ProdSupportOutcome,
)
from workspaces.data_engineering.agents.prod_support.ports import (
    AirflowFailureSource,
    ResourceDiscoveryInvoker,
    TaskLogUnavailableError,
)
from workspaces.data_engineering.agents.prod_support.reporting import format_reports
from workspaces.data_engineering.agents.prod_support.tools import (
    CLASSIFY_FAILURE,
    DISCOVER_FAILURES,
    FETCH_TASK_LOG,
    INSPECT_WORKLOAD,
    QUERY_OMS_JOB,
    TRIGGER_RESOURCE_DISCOVERY,
)

TASK_LOG_NOT_FOUND = 404
CLIENT_DAG_PREFIX = "l3-main-"
RESOURCE_DISCOVERY_TASK = "validate_event_bus_opportunities"

PROD_SUPPORT_DEFINITION = AgentDefinition(
    name="prod-support",
    description="Discover and diagnose production Airflow failures.",
    instructions=(
        "Run the deterministic replay workflow before repository exploration. "
        "Resolve dates from the request, parse every relevant Airflow record "
        "programmatically, and cite exact task-log evidence. Investigate US and "
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
        "Trigger the Resource Discovery agent for every unique resend client before "
        "selecting an application; preserve unresolved and ambiguous results. "
        "Treat exit code -9 as unknown_resource_termination: likely OOMed, and make "
        "a fix ticket "
        "when the attempt is greater than five. "
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
    version="6",
)


class ProdSupportAgent:
    """Discover, classify, and report Airflow failures."""

    def __init__(
        self,
        source: AirflowFailureSource,
        *,
        clock: Callable[[], datetime] | None = None,
        resource_discovery: ResourceDiscoveryInvoker | None = None,
    ) -> None:
        """Initialize with either a production or replay Airflow source."""
        self._source = source
        self._clock = clock or (lambda: datetime.now(UTC))
        self._resource_discovery = resource_discovery

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
            ),
        )

    async def investigate(self, prompt: str) -> ProdSupportOutcome:
        """Return structured evidence and reporting for benchmark evaluation."""
        reference_time = self._clock()
        window = resolve_query_window(prompt, reference_time)
        candidates = await self._source.discover_failures(window.failed_since)
        failures = tuple(
            failure for failure in candidates if failure.end_at >= window.failed_since
        )
        investigated = await asyncio.gather(
            *(self._investigate_failure(failure) for failure in failures)
        )
        hydrated = tuple(item[0] for item in investigated)
        diagnoses = tuple(item[1] for item in investigated)
        resource_results = await self._trigger_resource_discovery(hydrated)
        reports = format_reports(
            window.operational_date,
            hydrated,
            diagnoses,
            reference_date=reference_time.date(),
            resource_discovery_results=resource_results,
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
        """Resolve unique resend clients through the injected agent."""
        if self._resource_discovery is None:
            return ()
        client_ids = tuple(
            sorted(
                {
                    client_id
                    for failure in failures
                    if (client_id := _resend_client_id(failure)) is not None
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
        return tuple(
            await asyncio.gather(
                *(self._resource_discovery.run(request) for request in requests)
            )
        )

    async def _investigate_failure(
        self,
        failure: AirflowFailure,
    ) -> tuple[AirflowFailure, FailureDiagnosis]:
        """Hydrate and classify one failure independently."""
        try:
            log = failure.log or await self._source.fetch_log(failure)
        except TaskLogUnavailableError as error:
            if error.status_code != TASK_LOG_NOT_FOUND:
                raise
            diagnosis = FailureDiagnosis(
                failure_id=failure.failure_id,
                kind=FailureKind.UNKNOWN,
                confidence="evidence_gap",
                evidence=("Airflow task log unavailable: HTTP 404",),
            )
            return failure, diagnosis
        complete = _with_log(failure, log)
        return complete, classify_log(complete, log)


def _with_log(failure: AirflowFailure, log: str) -> AirflowFailure:
    return AirflowFailure(
        region=failure.region,
        dag_id=failure.dag_id,
        run_id=failure.run_id,
        task_id=failure.task_id,
        start_at=failure.start_at,
        end_at=failure.end_at,
        try_number=failure.try_number,
        log=log,
    )


def _resend_client_id(failure: AirflowFailure) -> str | None:
    """Return a validated client UUID for a resend-routing failure."""
    if failure.task_id != RESOURCE_DISCOVERY_TASK:
        return None
    if not failure.dag_id.startswith(CLIENT_DAG_PREFIX):
        return None
    candidate = failure.dag_id.removeprefix(CLIENT_DAG_PREFIX)
    try:
        return str(UUID(candidate))
    except ValueError:
        return None
