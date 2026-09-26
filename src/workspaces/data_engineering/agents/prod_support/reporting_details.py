"""Shared client, job-grouping, and remediation reporting helpers."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import NamedTuple
from uuid import UUID

from domain import AgentResult
from workspaces.data_engineering.agents.prod_support.models import (
    AirflowFailure,
    FailureDiagnosis,
)
from workspaces.data_engineering.agents.prod_support.reporting_config import (
    ProdSupportReportConfig,
)

CLIENT_DAG_PREFIX = "l3-main-"
RESEND_TASK = "validate_event_bus_opportunities"
LARGE_RESEND_THRESHOLD = 100
KPO_ATTEMPT_THRESHOLD = 5
MIN_GROUPED_SUBJECTS = 2
PAIR_SIZE = 2
TRUSTED_IDENTITY_STATUSES = frozenset({"unique", "user_confirmed", "reviewed"})
KPO_SIZER_AGENT_URI = "agent://kpo-sizer/definition"
RESEND_URLS = {
    "us01": (
        "https://us01-app.precisionlender.com/"
        "Admin/Troubleshooting/ResendOpportunitySnapshots"
    ),
    "us02": (
        "https://us02-app.precisionlender.com/"
        "Admin/Troubleshooting/ResendOpportunitySnapshots"
    ),
    "ent01": (
        "https://bacprod.precisionlender.com/"
        "Admin/Troubleshooting/ResendOpportunitySnapshots"
    ),
    "ca02": (
        "https://ca02-app.precisionlender.com/"
        "Admin/Troubleshooting/ResendOpportunitySnapshots"
    ),
}
UUID_PATTERN = re.compile(
    r"(?i)(?<![0-9a-f])"
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12})"
    r"(?![0-9a-f])"
)
EVENT_COUNT_PATTERN = re.compile(
    r"(?P<count>\d[\d,]*)\s+"
    r"(?:unique\s+)?(?:missing\s+)?(?:opportunity\s+)?"
    r"(?:snapshots?|events?)",
    re.IGNORECASE,
)


class ClientIdentity(NamedTuple):
    """Resolved identity and optional production routing metadata."""

    client_id: str
    name: str | None
    status: str
    environment: str | None
    reviewed_resend_url: str | None
    prod_support_ignore: bool


class FailureGroup(NamedTuple):
    """Failures grouped to minimize repeated clients and jobs."""

    subject_labels: tuple[str, ...]
    jobs: tuple[str, ...]
    failures: tuple[AirflowFailure, ...]


def client_identities(
    results: tuple[AgentResult, ...],
) -> dict[str, ClientIdentity]:
    """Index structured Resource Discovery results by client UUID."""
    identities: dict[str, ClientIdentity] = {}
    for result in results:
        attributes = dict(result.attributes)
        identifier = attributes.get("identifier_value")
        status = attributes.get("status")
        if not isinstance(identifier, str) or not isinstance(status, str):
            continue
        name = attributes.get("client_name")
        environment = attributes.get("environment")
        reviewed_resend_url = attributes.get("reviewed_production_resend_url")
        trusted = status in TRUSTED_IDENTITY_STATUSES
        identities[identifier] = ClientIdentity(
            client_id=identifier,
            name=name if trusted and isinstance(name, str) else None,
            status=status,
            environment=(
                environment if trusted and isinstance(environment, str) else None
            ),
            reviewed_resend_url=(
                reviewed_resend_url
                if trusted and isinstance(reviewed_resend_url, str)
                else None
            ),
            prod_support_ignore=attributes.get("prod_support_ignore") is True,
        )
    return identities


def client_id(failure: AirflowFailure) -> str | None:
    """Extract a validated client UUID from a DAG or task identifier."""
    candidates: list[str] = []
    if failure.dag_id.startswith(CLIENT_DAG_PREFIX):
        candidates.append(failure.dag_id.removeprefix(CLIENT_DAG_PREFIX))
    candidates.extend(UUID_PATTERN.findall(failure.task_id))
    for candidate in candidates:
        try:
            return str(UUID(candidate))
        except ValueError:
            continue
    return None


def failure_subject(
    failure: AirflowFailure,
    identities: dict[str, ClientIdentity],
) -> str:
    """Return a reviewed client label or a non-client recurring issue label."""
    identifier = client_id(failure)
    if identifier is None:
        if "market_insights" in failure.dag_id:
            return "Market Insights 3"
        if "subscriber" in failure.task_id:
            return "Subscriber validation"
        return failure.dag_id
    identity = identities.get(identifier)
    name = identity.name if identity is not None else None
    return f"{name or 'Unresolved client'} ({identifier[:3]})"


def subjects(
    failures: tuple[AirflowFailure, ...],
    identities: dict[str, ClientIdentity],
) -> str:
    """Return stable, de-duplicated subjects for a grouped job."""
    return _join_terms(
        tuple(
            dict.fromkeys(failure_subject(failure, identities) for failure in failures)
        )
    )


def identity_gap(
    failure: AirflowFailure,
    identities: dict[str, ClientIdentity],
) -> str:
    """Describe a missing unique Resource Discovery match."""
    identifier = client_id(failure)
    identity = identities.get(identifier or "")
    if identifier is None or (
        identity is not None
        and identity.status in TRUSTED_IDENTITY_STATUSES
        and identity.name is not None
    ):
        return ""
    status = identity.status if identity is not None else "not_found"
    return f"; Resource Discovery: no reviewed unique match ({status})"


def group_failures_by_job(
    failures: tuple[AirflowFailure, ...],
) -> tuple[tuple[str, tuple[AirflowFailure, ...]], ...]:
    """Group failures by a stable human-readable job label."""
    grouped: dict[str, list[AirflowFailure]] = {}
    for failure in failures:
        grouped.setdefault(job_label(failure.task_id), []).append(failure)
    return tuple(
        (job, tuple(sorted(items, key=_failure_sort_key)))
        for job, items in sorted(grouped.items())
    )


def group_failures_for_reporting(
    failures: tuple[AirflowFailure, ...],
    identities: dict[str, ClientIdentity],
) -> tuple[FailureGroup, ...]:
    """Group shared jobs or otherwise combine all jobs for one client."""
    grouped_ids: set[str] = set()
    groups: list[FailureGroup] = []
    for job, job_failures in group_failures_by_job(failures):
        job_subjects = tuple(
            dict.fromkeys(failure_subject(item, identities) for item in job_failures)
        )
        if len(job_subjects) < MIN_GROUPED_SUBJECTS:
            continue
        groups.append(FailureGroup(job_subjects, (job,), job_failures))
        grouped_ids.update(item.failure_id for item in job_failures)

    remaining_by_subject: dict[str, list[AirflowFailure]] = {}
    for failure in failures:
        if failure.failure_id not in grouped_ids:
            remaining_by_subject.setdefault(
                failure_subject(failure, identities),
                [],
            ).append(failure)
    for subject, subject_failures in remaining_by_subject.items():
        groups.append(
            FailureGroup(
                (subject,),
                tuple(
                    dict.fromkeys(job_label(item.task_id) for item in subject_failures)
                ),
                tuple(subject_failures),
            )
        )
    return tuple(
        sorted(
            groups,
            key=lambda group: (
                group.subject_labels,
                group.jobs,
            ),
        )
    )


def job_label(task_id: str) -> str:
    """Normalize common task identifiers to support-channel job names."""
    lowered = task_id.lower()
    if "delivery_to_promise_other_products" in lowered:
        return "D2P—Other Products"
    if "delivery_to_promise" in lowered:
        return "D2P"
    if "market_insights" in lowered or "mi_3" in lowered:
        return "MI3"
    if RESEND_TASK in lowered:
        return RESEND_TASK
    if "credit_migration_matrix" in lowered:
        return "CMM"
    return task_id.split(".", maxsplit=1)[0].replace("_", "-")


def include_in_data_internal(
    failure: AirflowFailure,
    config: ProdSupportReportConfig,
) -> bool:
    """Return whether a failure belongs in the concise channel message."""
    return not config.omits(failure)


def format_follow_up(
    operational_date: date,
    failures: tuple[AirflowFailure, ...],
    diagnoses: dict[str, FailureDiagnosis],
    identities: dict[str, ClientIdentity],
    config: ProdSupportReportConfig,
) -> str:
    """Render only explicit, approval-gated remediation choices."""
    if not failures:
        return "- No action is required."
    actions: list[str] = []
    resend_failures = tuple(
        failure for failure in failures if is_resend_failure(failure)
    )
    unique_resends: dict[tuple[str, str], AirflowFailure] = {}
    for failure in resend_failures:
        label = failure_subject(failure, identities)
        resend_date = logical_date(failure)
        key = label, resend_date
        previous = unique_resends.get(key)
        if previous is None or _resend_count(
            failure,
            diagnoses,
        ) > _resend_count(previous, diagnoses):
            unique_resends[key] = failure
    for (label, resend_date), failure in sorted(unique_resends.items()):
        count = event_count(diagnoses[failure.failure_id], failure.log)
        identity = identities.get(client_id(failure) or "")
        url = resend_url(
            identity.environment if identity is not None else None,
            identity.reviewed_resend_url if identity is not None else None,
        )
        if count is not None and count > LARGE_RESEND_THRESHOLD:
            actions.append(
                f"  - Follow up with pd-rix about {count:,} validate_event_bus "
                f"events for {label} on {resend_date}."
            )
        if url is None:
            actions.append(
                "  - Resolve the production resend application for "
                f"{label} before resending validate_event_bus events for "
                f"{resend_date}."
            )
        else:
            actions.append(
                f"  - [Resend validate_event_bus events for {label}]({url}) "
                f"for {resend_date}"
            )
    rerun_failures = tuple(
        failure
        for failure in failures
        if not is_resend_failure(failure) and include_in_data_internal(failure, config)
    )
    if rerun_failures:
        actions.append("  - Do you approve re-running the following jobs:")
        regions = sorted(
            {failure.region for failure in rerun_failures},
            key=lambda region: region.value,
        )
        for region in regions:
            regional = tuple(
                failure for failure in rerun_failures if failure.region is region
            )
            for group in group_failures_for_reporting(regional, identities):
                kpo = (
                    f"; also move to [KPO sizing agent]({KPO_SIZER_AGENT_URI})"
                    if any(
                        failure.try_number > KPO_ATTEMPT_THRESHOLD
                        for failure in group.failures
                    )
                    else ""
                )
                actions.append(
                    f"    - {_join_terms(group.subject_labels)}: "
                    f"{_join_terms(group.jobs)} for "
                    f"{operational_date.isoformat()}{kpo}"
                )
    if not actions:
        return "- No action is required."
    return "\n".join(("- Would you like to:", *actions))


def logical_date(failure: AirflowFailure) -> str:
    """Return the Airflow logical date used for a resend action."""
    _, separator, timestamp = failure.run_id.partition("__")
    if separator:
        try:
            return datetime.fromisoformat(timestamp).date().isoformat()
        except ValueError:
            pass
    return failure.start_at.date().isoformat()


def resend_url(
    environment: str | None,
    reviewed_url: str | None = None,
) -> str | None:
    """Return the reviewed production resend URL for an environment."""
    del environment
    if reviewed_url is not None and reviewed_url in RESEND_URLS.values():
        return reviewed_url
    return None


def event_count(diagnosis: FailureDiagnosis, log: str = "") -> int | None:
    """Return the largest event count stated in diagnosis evidence or its log."""
    counts = [
        int(match.group("count").replace(",", ""))
        for evidence in (*diagnosis.evidence, log)
        for match in EVENT_COUNT_PATTERN.finditer(evidence)
    ]
    return max(counts, default=None)


def is_resend_failure(failure: AirflowFailure) -> bool:
    """Return whether a nested or direct task is event-bus validation."""
    return RESEND_TASK in failure.task_id.lower()


def _resend_count(
    failure: AirflowFailure,
    diagnoses: dict[str, FailureDiagnosis],
) -> int:
    """Return a sortable resend count when evidence contains one."""
    return event_count(diagnoses[failure.failure_id], failure.log) or 0


def _failure_sort_key(failure: AirflowFailure) -> tuple[object, ...]:
    """Return deterministic ordering for report groups."""
    return (
        failure.region.value,
        failure.dag_id,
        failure.task_id,
        failure.run_id,
        failure.try_number,
    )


def _join_terms(values: tuple[str, ...]) -> str:
    """Join compact labels using natural-language punctuation."""
    if len(values) < PAIR_SIZE:
        return "".join(values)
    if len(values) == PAIR_SIZE:
        return " and ".join(values)
    return f"{', '.join(values[:-1])}, and {values[-1]}"
