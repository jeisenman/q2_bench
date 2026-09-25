"""Production-support agent orchestrator."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

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
    ProdSupportOutcome,
)
from workspaces.data_engineering.agents.prod_support.ports import (
    AirflowFailureSource,
)
from workspaces.data_engineering.agents.prod_support.reporting import format_report
from workspaces.data_engineering.agents.prod_support.tools import (
    CLASSIFY_FAILURE,
    DISCOVER_FAILURES,
    FETCH_TASK_LOG,
)

PROD_SUPPORT_DEFINITION = AgentDefinition(
    name="prod-support",
    description="Discover and diagnose production Airflow failures.",
    instructions=(
        "Run the deterministic replay workflow before repository exploration. "
        "Resolve dates from the request, parse every relevant Airflow record "
        "programmatically, and cite exact task-log evidence. Investigate US and "
        "CA concurrently. Use Airflow for batch evidence and query OMS only "
        "with exact identifiers when corroboration is required. Diagnose "
        "independently before reading curated expectations. Keep tool output "
        "targeted, run the repository quality check when changing code, and "
        "never mutate production systems."
    ),
    tools=(DISCOVER_FAILURES, FETCH_TASK_LOG, CLASSIFY_FAILURE),
    version="2",
)


class ProdSupportAgent:
    """Discover, classify, and report Airflow failures."""

    def __init__(
        self,
        source: AirflowFailureSource,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Initialize with either a production or replay Airflow source."""
        self._source = source
        self._clock = clock or (lambda: datetime.now(UTC))

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
        report = format_report(
            window.operational_date,
            hydrated,
            diagnoses,
            reference_date=reference_time.date(),
        )
        return ProdSupportOutcome(
            operational_date=window.operational_date,
            failed_since=window.failed_since,
            failures=hydrated,
            diagnoses=diagnoses,
            report=report,
        )

    async def _investigate_failure(
        self,
        failure: AirflowFailure,
    ) -> tuple[AirflowFailure, FailureDiagnosis]:
        """Hydrate and classify one failure independently."""
        log = failure.log or await self._source.fetch_log(failure)
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
