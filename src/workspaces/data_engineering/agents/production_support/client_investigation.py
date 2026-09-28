"""Client-scoped production failure investigation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from domain import AgentRequest, AgentResult
from workspaces.data_engineering.agents.production_support.failure_tools import (
    FailureDiscoveryTool,
)
from workspaces.data_engineering.agents.production_support.follow_up import FollowUp
from workspaces.data_engineering.agents.production_support.investigation import (
    FailureInvestigator,
    InvestigationServices,
)
from workspaces.data_engineering.agents.production_support.models import (
    AirflowFailure,
    FailureDiagnosis,
    Region,
)
from workspaces.data_engineering.agents.production_support.ports import (
    AirflowFailureSource,
    ResourceDiscoveryInvoker,
)
from workspaces.data_engineering.agents.production_support.report_findings import (
    ReportFindings,
)
from workspaces.data_engineering.agents.production_support.reporting_config import (
    ProdSupportReportConfig,
)
from workspaces.data_engineering.agents.production_support.reporting_details import (
    client_identities,
)
from workspaces.data_engineering.agents.production_support.triage_manager import (
    TriageManager,
)

CLIENT_DAG_PREFIX = "l3-main-"


class ClientInvestigationError(ValueError):
    """Raised when a client-scoped investigation request is invalid."""

    @classmethod
    def invalid_client_guuid(cls) -> ClientInvestigationError:
        """Return an error for an incomplete or malformed client UUID."""
        return cls("client_guuid must be a complete UUID")

    @classmethod
    def noncanonical_client_guuid(cls) -> ClientInvestigationError:
        """Return an error for a UUID without canonical hyphenation."""
        return cls("client_guuid must use canonical hyphenated UUID form")

    @classmethod
    def naive_clock(cls) -> ClientInvestigationError:
        """Return an error for a clock without timezone information."""
        return cls("clock must return a timezone-aware datetime")

    @classmethod
    def invalid_since(cls) -> ClientInvestigationError:
        """Return an error for a malformed explicit cutoff."""
        return cls("since must be an ISO-8601 datetime")

    @classmethod
    def naive_since(cls) -> ClientInvestigationError:
        """Return an error for a cutoff without timezone information."""
        return cls("since must include a timezone offset")


class ClientFailureWorkflow:
    """Resolve one client and investigate only its exact Airflow DAG."""

    def __init__(
        self,
        source: AirflowFailureSource,
        *,
        resource_discovery: ResourceDiscoveryInvoker | None = None,
        investigation: InvestigationServices | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Initialize the read-only client investigation workflow."""
        services = investigation or InvestigationServices()
        self._source = source
        self._failure_discovery = FailureDiscoveryTool(source)
        self._resource_discovery = resource_discovery
        self._clock = clock or (lambda: datetime.now(UTC))
        self._triage = TriageManager(
            FailureInvestigator(
                source,
                prior_logs=services.prior_logs,
                task_metadata=services.task_metadata,
                oms=services.oms,
            ),
            max_parallel=services.max_parallel,
        )

    async def investigate_client_failures(
        self,
        client_guuid: str,
        since: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, object]:
        """Resolve a client UUID and diagnose failures on its exact L3 DAG."""
        client_id = _canonical_client_id(client_guuid)
        failed_since = _resolve_since(since, self._clock())
        resource_results = await self._resolve_client(client_id, correlation_id)
        dag_id = f"{CLIENT_DAG_PREFIX}{client_id}"
        failures = tuple(
            sorted(
                await self._failure_discovery.discover_client(
                    dag_id,
                    failed_since,
                ),
                key=lambda item: (
                    item.end_at,
                    item.region.value,
                    item.run_id,
                    item.task_id,
                    item.try_number,
                ),
                reverse=True,
            )
        )
        investigated = await self._triage.triage(failures)
        hydrated = tuple(item[0] for item in investigated)
        diagnoses = tuple(item[1] for item in investigated)
        findings = ReportFindings(
            failures=hydrated,
            diagnoses=diagnoses,
            resource_discovery_results=resource_results,
            config=ProdSupportReportConfig(),
            regions=(
                tuple(dict.fromkeys(item.region for item in hydrated))
                or (Region.US_01, Region.CA_02)
            ),
        )
        identities = client_identities(resource_results)
        identity = identities.get(client_id)
        client_name = identity.name if identity is not None else None
        follow_up = FollowUp().render(failed_since.date(), findings)
        return {
            "client_guuid": client_id,
            "client_name": client_name,
            "resource_discovery_status": (
                identity.status if identity is not None else "not_configured"
            ),
            "dag_id": dag_id,
            "failed_since": failed_since.isoformat(),
            "failure_count": len(hydrated),
            "summary": _developer_summary(
                f"{client_name or 'Unresolved client'} ({client_id})",
                failed_since,
                hydrated,
                diagnoses,
                follow_up,
            ),
            "failures": [
                _failure_output(failure, diagnosis)
                for failure, diagnosis in zip(hydrated, diagnoses, strict=True)
            ],
            "follow_up": follow_up,
            "mutation_performed": False,
        }

    async def _resolve_client(
        self,
        client_id: str,
        correlation_id: str | None,
    ) -> tuple[AgentResult, ...]:
        """Resolve the exact client UUID before querying Airflow."""
        if self._resource_discovery is None:
            return ()
        result = await self._resource_discovery.run(
            AgentRequest(
                prompt=f"Resolve production resources for client {client_id}.",
                correlation_id=correlation_id or f"client-failure-{client_id}",
                attributes=(
                    ("identifier_kind", "client_id"),
                    ("identifier_value", client_id),
                ),
            )
        )
        return (result,)


def _canonical_client_id(value: str) -> str:
    """Return a canonical complete UUID or fail before external reads."""
    try:
        parsed = UUID(value)
    except (AttributeError, TypeError, ValueError) as error:
        raise ClientInvestigationError.invalid_client_guuid() from error
    canonical = str(parsed)
    if value.lower() != canonical:
        raise ClientInvestigationError.noncanonical_client_guuid()
    return canonical


def _resolve_since(value: str | None, reference_time: datetime) -> datetime:
    """Return an explicit cutoff or the prior 05:00 UTC operational anchor."""
    if reference_time.tzinfo is None:
        raise ClientInvestigationError.naive_clock()
    if value is not None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ClientInvestigationError.invalid_since() from error
        if parsed.tzinfo is None:
            raise ClientInvestigationError.naive_since()
        return parsed.astimezone(UTC)
    prior_date = reference_time.astimezone(UTC).date() - timedelta(days=1)
    return datetime.combine(prior_date, time(hour=5), tzinfo=UTC)


def _failure_output(
    failure: AirflowFailure,
    diagnosis: FailureDiagnosis,
) -> dict[str, object]:
    """Return structured, non-secret evidence for one failed task."""
    return {
        "region": failure.region.value,
        "run_id": failure.run_id,
        "task_id": failure.task_id,
        "try_number": failure.try_number,
        "start_at": failure.start_at.isoformat(),
        "end_at": failure.end_at.isoformat(),
        "classification": diagnosis.kind.value,
        "confidence": diagnosis.confidence,
        "evidence_source": diagnosis.source.value,
        "evidence_status": diagnosis.status.value,
        "evidence": list(diagnosis.evidence),
        "distinctness_checks": [
            {
                "dataset": check.dataset,
                "total": check.total,
                "unique": check.unique,
                "status": check.status,
            }
            for check in diagnosis.distinctness_checks
        ],
        "rerun_targets": list(diagnosis.rerun_targets),
    }


def _developer_summary(
    label: str,
    failed_since: datetime,
    failures: tuple[AirflowFailure, ...],
    diagnoses: tuple[FailureDiagnosis, ...],
    follow_up: str,
) -> str:
    """Render a concise developer-readable client diagnosis."""
    if not failures:
        return (
            f"No failed task instances were found for {label} ending at or after "
            f"{failed_since.isoformat()}.\n\nSuggested follow-up:\n{follow_up}"
        )
    lines = [
        f"{label} has {len(failures)} failed task instance(s) ending at or after "
        f"{failed_since.isoformat()}:"
    ]
    for failure, diagnosis in zip(failures, diagnoses, strict=True):
        evidence = (
            diagnosis.evidence[0] if diagnosis.evidence else "no terminal evidence"
        )
        lines.append(
            f"- {failure.region.value} {failure.task_id}, run {failure.run_id}, "
            f"attempt {failure.try_number}: {diagnosis.kind.value}; {evidence}"
        )
        if diagnosis.rerun_targets:
            lines.append(
                f"  Upstream rerun target: {', '.join(diagnosis.rerun_targets)}"
            )
    lines.extend(("", "Suggested follow-up:", follow_up))
    return "\n".join(lines)
