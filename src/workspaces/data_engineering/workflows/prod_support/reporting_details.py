"""Shared client, job-grouping, and remediation reporting helpers."""

from __future__ import annotations

import re
from typing import NamedTuple
from uuid import UUID

from domain import AgentResult
from workspaces.data_engineering.workflows.prod_support.models import (
    AirflowFailure,
    FailureDiagnosis,
)
from workspaces.data_engineering.workflows.prod_support.reporting_config import (
    ProdSupportReportConfig,
)

CLIENT_DAG_PREFIX = "l3-main-"
RESEND_TASK = "validate_event_bus_opportunities"
EVENT_BUS_HISTORY_TASK = "get_opp_history_params"
EVENT_BUS_DAG = "event_bus_to_payloads_historical"
HIDDEN_REPORT_TASKS = frozenset({"log_cleanup", "expire_logs_3"})
JOB_LABEL_RULES = (
    (EVENT_BUS_HISTORY_TASK, EVENT_BUS_DAG),
    ("delivery_to_promise_other_products", "D2P—Other Products"),
    ("delivery_to_promise", "D2P"),
    ("market_insights_3", "MI3"),
    ("market_insights", "MI3"),
    (RESEND_TASK, RESEND_TASK),
    ("credit_migration_matrix", "CMM"),
)
MIN_GROUPED_SUBJECTS = 2
PAIR_SIZE = 2
TRUSTED_IDENTITY_STATUSES = frozenset({"unique", "user_confirmed", "reviewed"})
DATA_INTERNAL_CLIENT_ABBREVIATIONS = (
    ("scotiabank - data validation", "Scotiabank DV"),
    ("wells fargo", "WF"),
    ("city national bank", "CNB"),
    ("bank of america", "BoFA"),
    ("bofa", "BoFA"),
    ("cibc canada", "CIBC CA"),
)
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
OPPORTUNITY_ID_PATTERN = re.compile(
    r"OpportunityId:\s*([0-9a-f-]{36})",
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


def data_internal_client_identities(
    results: tuple[AgentResult, ...],
) -> dict[str, ClientIdentity]:
    """Return identities with the channel-only client abbreviations applied."""
    identities = client_identities(results)
    return {
        identifier: identity._replace(name=_data_internal_name(identity.name))
        for identifier, identity in identities.items()
    }


def _data_internal_name(name: str | None) -> str | None:
    """Return the approved compact Data Internal client name."""
    if name is None:
        return None
    normalized = name.casefold().strip()
    return next(
        (
            abbreviation
            for prefix, abbreviation in DATA_INTERNAL_CLIENT_ABBREVIATIONS
            if normalized.startswith(prefix)
        ),
        name,
    )


def client_id(failure: AirflowFailure) -> str | None:
    """Extract a validated client UUID from a DAG or task identifier."""
    identifiers = client_ids(failure)
    return identifiers[0] if identifiers else None


def client_ids(failure: AirflowFailure) -> tuple[str, ...]:
    """Extract all validated client UUIDs associated with one failure."""
    candidates: list[str] = []
    if failure.dag_id.startswith(CLIENT_DAG_PREFIX):
        candidates.append(failure.dag_id.removeprefix(CLIENT_DAG_PREFIX))
    candidates.extend(UUID_PATTERN.findall(failure.task_id))
    if failure.dag_id == EVENT_BUS_DAG and failure.task_id == EVENT_BUS_HISTORY_TASK:
        candidates.extend(client_ids_from_text(failure.log))
    identifiers: list[str] = []
    for candidate in candidates:
        try:
            identifier = str(UUID(candidate))
        except ValueError:
            continue
        if identifier not in identifiers:
            identifiers.append(identifier)
    return tuple(identifiers)


def client_ids_from_text(text: str) -> tuple[str, ...]:
    """Extract normalized client UUIDs from evidence text."""
    identifiers: list[str] = []
    for candidate in UUID_PATTERN.findall(text):
        try:
            identifier = str(UUID(candidate))
        except ValueError:
            continue
        if identifier not in identifiers:
            identifiers.append(identifier)
    return tuple(identifiers)


def failure_subject_for_identifier(
    identifier: str,
    identities: dict[str, ClientIdentity],
) -> str:
    """Return the reviewed subject label for one client UUID."""
    identity = identities.get(identifier)
    name = identity.name if identity is not None else None
    return f"{name or 'Unresolved client'} ({identifier[:3]})"


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
    return failure_subject_for_identifier(identifier, identities)


def failure_subjects(
    failure: AirflowFailure,
    identities: dict[str, ClientIdentity],
) -> tuple[str, ...]:
    """Return every client subject represented by one failure."""
    identifiers = client_ids(failure)
    if identifiers:
        return tuple(
            failure_subject_for_identifier(identifier, identities)
            for identifier in identifiers
        )
    return (failure_subject(failure, identities),)


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
    failures = tuple(item for item in failures if not is_hidden_from_report(item))
    grouped_ids: set[str] = set()
    groups: list[FailureGroup] = []
    for job, job_failures in group_failures_by_job(failures):
        job_subjects = tuple(
            dict.fromkeys(
                subject
                for item in job_failures
                for subject in failure_subjects(item, identities)
            )
        )
        if job == RESEND_TASK or len(job_subjects) < MIN_GROUPED_SUBJECTS:
            continue
        groups.append(FailureGroup(job_subjects, (job,), job_failures))
        grouped_ids.update(item.failure_id for item in job_failures)

    remaining_by_subject: dict[str, list[AirflowFailure]] = {}
    for failure in failures:
        if failure.failure_id not in grouped_ids:
            for subject in failure_subjects(failure, identities):
                remaining_by_subject.setdefault(subject, []).append(failure)
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
    """Normalize aliases while preserving underscores in task identifiers."""
    lowered = task_id.lower()
    for marker, label in JOB_LABEL_RULES:
        if marker in lowered:
            return label
    if "mi_3" in lowered:
        return "MI3"
    return task_id.split(".", maxsplit=1)[0]


def include_in_data_internal(
    failure: AirflowFailure,
    config: ProdSupportReportConfig,
) -> bool:
    """Return whether a failure belongs in the concise channel message."""
    return not is_hidden_from_report(failure) and config.omission_group(failure) is None


def is_hidden_from_report(failure: AirflowFailure) -> bool:
    """Return whether a non-actionable maintenance task is report-suppressed."""
    return job_label(failure.task_id) in HIDDEN_REPORT_TASKS or (
        failure.dag_id.casefold() in HIDDEN_REPORT_TASKS
    )


def event_count(diagnosis: FailureDiagnosis, log: str = "") -> int | None:
    """Return the largest stated count or unique captured opportunity-ID count."""
    sources = (*diagnosis.evidence, log)
    counts = [
        int(match.group("count").replace(",", ""))
        for evidence in sources
        for match in EVENT_COUNT_PATTERN.finditer(evidence)
    ]
    opportunity_ids = {
        match.group(1).lower()
        for evidence in sources
        for match in OPPORTUNITY_ID_PATTERN.finditer(evidence)
    }
    return max((*counts, len(opportunity_ids)), default=None) or None


def is_resend_failure(failure: AirflowFailure) -> bool:
    """Return whether a task requires event-resend handling."""
    lowered = failure.task_id.lower()
    return RESEND_TASK in lowered or (
        failure.dag_id == EVENT_BUS_DAG and EVENT_BUS_HISTORY_TASK in lowered
    )


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
