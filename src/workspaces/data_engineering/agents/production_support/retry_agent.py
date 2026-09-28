"""Map conversational follow-up directions to safe Airflow retry plans."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping

from domain import AgentDefinition
from observability import traced_operation
from workspaces.data_engineering.agents.production_support.models import (
    AirflowFailure,
    Region,
    RetryCandidate,
)
from workspaces.data_engineering.agents.production_support.ports import (
    AirflowRetrySource,
)
from workspaces.data_engineering.agents.production_support.report_findings import (
    ReportFindings,
)
from workspaces.data_engineering.agents.production_support.reporting_details import (
    ClientIdentity,
    client_id,
    client_identities,
    failure_subject,
    is_resend_failure,
    job_label,
)
from workspaces.data_engineering.agents.production_support.retry_models import (
    RetryBatch,
    RetryTaskReference,
)
from workspaces.data_engineering.agents.production_support.tools import (
    EXECUTE_AIRFLOW_RETRIES,
)

NUMBER_PATTERN = re.compile(r"\b\d+\b")
EXCLUSION_PATTERN = re.compile(
    r"(?:don't|do not|except|exclude)\s+(?:do\s+)?(?P<values>.*)",
    re.IGNORECASE,
)
PROD_SUPPORT_FOLLOW_UP_DEFINITION = AgentDefinition(
    name="prod-support.follow-up",
    description="Map operator follow-up directions to exact Airflow retries.",
    instructions=(
        "Receive follow-up direction after a production-support run. Keep every "
        "candidate's source Airflow region. Interpret 'follow up', 'retry CA', "
        "'retry all jobs', or numbered include/exclude requests as authorization "
        "to execute the exact selected tasks immediately. Return the original US "
        "and CA validation links after execution. Never retry verified omissions, "
        "resend tasks, unresolved clients, upstream, downstream, past, or future tasks."
    ),
    tools=(EXECUTE_AIRFLOW_RETRIES,),
    version="1",
)


class RetryDirectionError(ValueError):
    """Raised when follow-up direction cannot select safe retry candidates."""

    @classmethod
    def direction_required(cls) -> RetryDirectionError:
        """Return an error for a non-follow-up request."""
        return cls("follow-up direction must request retry or follow up")

    @classmethod
    def empty_selection(cls) -> RetryDirectionError:
        """Return an error when no eligible retry target was selected."""
        return cls("follow-up direction selected no retry candidates")

    @classmethod
    def unknown_candidates(cls, values: str) -> RetryDirectionError:
        """Return an error for unknown numbered candidates."""
        return cls(f"unknown retry candidate numbers: {values}")


class FollowUpAgent:
    """Execute exact Airflow retries authorized by a developer follow-up."""

    definition = PROD_SUPPORT_FOLLOW_UP_DEFINITION

    def __init__(self, source: AirflowRetrySource) -> None:
        """Initialize with an injected production retry boundary."""
        self._source = source

    async def execute(
        self,
        direction: str,
        candidates: tuple[RetryCandidate, ...],
    ) -> tuple[RetryTaskReference, ...]:
        """Select and execute retries from one developer follow-up."""
        async with traced_operation(
            "agent.prod-support-follow-up.execute",
            attributes={
                "q2.agent.name": self.definition.name,
                "q2.agent.candidate_count": len(candidates),
            },
        ):
            return await self._execute(direction, candidates)

    async def _execute(
        self,
        direction: str,
        candidates: tuple[RetryCandidate, ...],
    ) -> tuple[RetryTaskReference, ...]:
        """Execute the selected retries within the trace span."""
        selected = select_retry_candidates(direction, candidates)
        batches = retry_batches(selected)
        references: list[RetryTaskReference] = []
        for batch in batches:
            references.extend(await self._source.execute_retry(batch, direction))
        return tuple(references)


def retry_candidates(findings: ReportFindings) -> tuple[RetryCandidate, ...]:
    """Return numbered retry candidates after safety and identity filtering."""
    identities = client_identities(findings.resource_discovery_results)
    eligible = tuple(
        failure
        for failure in findings.failures
        if not is_resend_failure(failure)
        and findings.config.configured_omission_group(failure) is None
        and _identity_resolved(failure, identities)
    )
    return tuple(
        RetryCandidate(
            number=index,
            region=failure.region,
            dag_id=failure.dag_id,
            run_id=failure.run_id,
            task_id=failure.task_id,
            label=(
                f"{failure_subject(failure, identities)}: {job_label(failure.task_id)}"
            ),
        )
        for index, failure in enumerate(eligible, start=1)
    )


def select_retry_candidates(
    direction: str,
    candidates: tuple[RetryCandidate, ...],
) -> tuple[RetryCandidate, ...]:
    """Select candidates by ordinal, region, or all-jobs follow-up wording."""
    lowered = direction.casefold()
    if "retry" not in lowered and "follow up" not in lowered:
        raise RetryDirectionError.direction_required()
    exclusion = EXCLUSION_PATTERN.search(direction)
    included_text = direction[: exclusion.start()] if exclusion else direction
    included_numbers = {int(value) for value in NUMBER_PATTERN.findall(included_text)}
    excluded_numbers = (
        {int(value) for value in NUMBER_PATTERN.findall(exclusion.group("values"))}
        if exclusion
        else set()
    )
    region = (
        Region.CA_02
        if re.search(r"\bca(?:-?02)?\b", lowered)
        else Region.US_01
        if re.search(r"\bus(?:-?01)?\b", lowered)
        else None
    )
    selected = tuple(
        candidate
        for candidate in candidates
        if (not included_numbers or candidate.number in included_numbers)
        and candidate.number not in excluded_numbers
        and (region is None or candidate.region is region)
    )
    unknown = (included_numbers | excluded_numbers) - {
        candidate.number for candidate in candidates
    }
    if unknown:
        values = ", ".join(map(str, sorted(unknown)))
        raise RetryDirectionError.unknown_candidates(values)
    if not selected:
        raise RetryDirectionError.empty_selection()
    return selected


def retry_batches(
    candidates: tuple[RetryCandidate, ...],
) -> tuple[RetryBatch, ...]:
    """Group selected tasks into exact regional DAG-run clear requests."""
    grouped: defaultdict[tuple[Region, str, str], list[str]] = defaultdict(list)
    for candidate in candidates:
        grouped[(candidate.region, candidate.dag_id, candidate.run_id)].append(
            candidate.task_id
        )
    return tuple(
        RetryBatch(region, dag_id, run_id, tuple(dict.fromkeys(task_ids)))
        for (region, dag_id, run_id), task_ids in sorted(
            grouped.items(),
            key=lambda item: tuple(str(value) for value in item[0]),
        )
    )


def _identity_resolved(
    failure: AirflowFailure,
    identities: Mapping[str, ClientIdentity],
) -> bool:
    identifier = client_id(failure)
    if identifier is None:
        return True
    identity = identities.get(identifier)
    return bool(identity is not None and getattr(identity, "name", None))
