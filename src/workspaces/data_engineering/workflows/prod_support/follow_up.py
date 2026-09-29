"""Render approval-gated production-support follow-up actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from workspaces.data_engineering.workflows.prod_support.models import (
    AirflowFailure,
    FailureDiagnosis,
)
from workspaces.data_engineering.workflows.prod_support.report_findings import (
    ReportFindings,
)
from workspaces.data_engineering.workflows.prod_support.reporting_details import (
    ClientIdentity,
    FailureGroup,
    client_identities,
    client_ids,
    event_count,
    failure_subject,
    failure_subject_for_identifier,
    failure_subjects,
    group_failures_for_reporting,
    is_hidden_from_report,
    is_resend_failure,
)

LARGE_RESEND_THRESHOLD = 100
KPO_ATTEMPT_THRESHOLD = 5
PAIR_SIZE = 2
KPO_SIZER_AGENT_URI = "agent://kpo-sizer/definition"
RESEND_URLS = frozenset(
    {
        (
            "https://us01-app.precisionlender.com/"
            "Admin/Troubleshooting/ResendOpportunitySnapshots"
        ),
        (
            "https://us02-app.precisionlender.com/"
            "Admin/Troubleshooting/ResendOpportunitySnapshots"
        ),
        (
            "https://bacprod.precisionlender.com/"
            "Admin/Troubleshooting/ResendOpportunitySnapshots"
        ),
        (
            "https://cac01-app.precisionlender.com/"
            "Admin/Troubleshooting/ResendSnapshotsForClient"
        ),
    }
)


@dataclass(frozen=True, slots=True)
class ResendCandidate:
    """One deduplicated client/date resend candidate."""

    label: str
    resend_date: str
    count: int | None
    url: str | None


class FollowUp:
    """Render read-only remediation choices without executing them."""

    def render(
        self,
        operational_date: date,
        findings: ReportFindings,
    ) -> str:
        """Return actionable resend and approval-gated rerun choices."""
        return _format_follow_up(
            operational_date,
            findings.failures,
            {item.failure_id: item for item in findings.diagnoses},
            client_identities(findings.resource_discovery_results),
        )


def _format_follow_up(
    operational_date: date,
    failures: tuple[AirflowFailure, ...],
    diagnoses: dict[str, FailureDiagnosis],
    identities: dict[str, ClientIdentity],
) -> str:
    """Render explicit remediation choices with human help for evidence gaps."""
    if not failures:
        return "- No action is required."
    actionable_failures = tuple(
        failure for failure in failures if not is_hidden_from_report(failure)
    )
    if not actionable_failures:
        return "- No action is required."
    unresolved = _unresolved_client_labels(actionable_failures, identities)
    actions = (
        [
            "- Ask a human to resolve the client identity for "
            f"{_join_terms(unresolved)} before proposing remediation for date "
            f"{operational_date.strftime('%m-%d-%y')}."
        ]
        if unresolved
        else []
    )
    actions.extend(_resend_actions(actionable_failures, diagnoses, identities))
    rerun_failures = tuple(
        failure
        for failure in actionable_failures
        if not is_resend_failure(failure)
        and not _has_unresolved_client(failure, identities)
    )
    if rerun_failures:
        actions.append("- Would you like to re-run:")
        regions = sorted(
            {failure.region for failure in rerun_failures},
            key=lambda region: region.value,
        )
        for region in regions:
            regional = tuple(
                failure for failure in rerun_failures if failure.region is region
            )
            for group in _group_reruns_by_subject(regional, identities):
                kpo = (
                    f"; also move to [KPO sizing agent]({KPO_SIZER_AGENT_URI})"
                    if any(
                        failure.try_number > KPO_ATTEMPT_THRESHOLD
                        for failure in group.failures
                    )
                    else ""
                )
                dag_ids = tuple(
                    dict.fromkeys(failure.dag_id for failure in group.failures)
                )
                displayed_dag_ids = tuple(
                    dag_id for dag_id in dag_ids if dag_id not in group.subject_labels
                )
                dag_text = (
                    f" {_join_terms(displayed_dag_ids)}" if displayed_dag_ids else ""
                )
                job_suffix = "job" if len(group.jobs) == 1 else "jobs"
                actions.append(
                    f"  - {_join_terms(group.subject_labels)}{dag_text} "
                    f"{_join_terms(group.jobs)} "
                    f"{job_suffix}{kpo}"
                )
    if not actions:
        return "- No action is required."
    return "\n".join(actions)


def _group_reruns_by_subject(
    failures: tuple[AirflowFailure, ...],
    identities: dict[str, ClientIdentity],
) -> tuple[FailureGroup, ...]:
    """Group rerun choices by one client so bullets never combine clients."""
    grouped = group_failures_for_reporting(failures, identities)
    by_subject: dict[str, list[AirflowFailure]] = {}
    for group in grouped:
        for failure in group.failures:
            subject = failure_subject(failure, identities)
            by_subject.setdefault(subject, []).append(failure)
    return tuple(
        FailureGroup(
            (subject,),
            tuple(
                dict.fromkeys(
                    job for failure in subject_failures for job in _rerun_jobs(failure)
                )
            ),
            tuple(subject_failures),
        )
        for subject, subject_failures in sorted(by_subject.items())
    )


def _rerun_jobs(failure: AirflowFailure) -> tuple[str, ...]:
    """Return concise task names while preserving validated task identity."""
    return (failure.task_id.rsplit(".", maxsplit=1)[-1],)


def _unresolved_client_labels(
    failures: tuple[AirflowFailure, ...],
    identities: dict[str, ClientIdentity],
) -> tuple[str, ...]:
    """Return stable unresolved client labels requiring human resolution."""
    return tuple(
        sorted(
            {
                subject
                for failure in failures
                if _has_unresolved_client(failure, identities)
                for subject in failure_subjects(failure, identities)
            }
        )
    )


def _has_unresolved_client(
    failure: AirflowFailure,
    identities: dict[str, ClientIdentity],
) -> bool:
    """Return whether a client-scoped failure lacks a reviewed identity."""
    identifiers = client_ids(failure)
    if not identifiers:
        return False
    return any(
        (identity := identities.get(identifier)) is None or identity.name is None
        for identifier in identifiers
    )


def _resend_actions(
    failures: tuple[AirflowFailure, ...],
    diagnoses: dict[str, FailureDiagnosis],
    identities: dict[str, ClientIdentity],
) -> tuple[str, ...]:
    """Group resend actions by approved destination and logical date."""
    candidates = _resend_candidates(failures, diagnoses, identities)
    missing_routes: dict[str, list[str]] = {}
    missing_counts: dict[tuple[str, str], list[str]] = {}
    actionable: dict[tuple[str, str], list[ResendCandidate]] = {}
    large_unrouted: list[ResendCandidate] = []
    for candidate in candidates:
        if candidate.url is None:
            missing_routes.setdefault(candidate.resend_date, []).append(candidate.label)
            if candidate.count is not None and candidate.count > LARGE_RESEND_THRESHOLD:
                large_unrouted.append(candidate)
        elif candidate.count is None:
            missing_counts.setdefault(
                (candidate.resend_date, candidate.url),
                [],
            ).append(candidate.label)
        else:
            actionable.setdefault(
                (candidate.resend_date, candidate.url),
                [],
            ).append(candidate)

    actions = [
        f"- Follow up with pd-rix about {candidate.count:,} opportunities "
        f"for {candidate.label} for date {candidate.resend_date}."
        for candidate in large_unrouted
        if candidate.count is not None
    ]
    actions.extend(
        "- Ask a human to identify the production resend application "
        f"environment for {_join_terms(tuple(labels))} for date {resend_date}."
        for resend_date, labels in sorted(missing_routes.items())
    )
    actions.extend(
        "- Ask a human to confirm the opportunity count for "
        f"{_join_terms(tuple(labels))} on "
        f"[Resend Opportunity Snapshots]({url}) for date {resend_date}."
        for (resend_date, url), labels in sorted(missing_counts.items())
    )
    for (resend_date, url), grouped in sorted(actionable.items()):
        labels = tuple(candidate.label for candidate in grouped)
        count = sum(candidate.count or 0 for candidate in grouped)
        if count > LARGE_RESEND_THRESHOLD:
            actions.append(
                f"- Follow up with pd-rix about {count:,} opportunities for "
                f"{_join_terms(labels)} on [Resend Opportunity Snapshots]({url}) "
                f"for date {resend_date}."
            )
        actions.append(
            f"- Send events for {_join_terms(labels)} on "
            f"[Resend Opportunity Snapshots]({url}) for date {resend_date}."
        )
    return tuple(actions)


def _resend_candidates(
    failures: tuple[AirflowFailure, ...],
    diagnoses: dict[str, FailureDiagnosis],
    identities: dict[str, ClientIdentity],
) -> tuple[ResendCandidate, ...]:
    """Deduplicate repeated client/date failures using the largest known count."""
    selected: dict[tuple[str, str], ResendCandidate] = {}
    for failure in failures:
        if not is_resend_failure(failure) or _has_unresolved_client(
            failure,
            identities,
        ):
            continue
        resend_date = _logical_date(failure).strftime("%m-%d-%y")
        for identifier in client_ids(failure):
            identity = identities.get(identifier)
            label = failure_subject_for_identifier(identifier, identities)
            reviewed_url = (
                identity.reviewed_resend_url if identity is not None else None
            )
            candidate = ResendCandidate(
                label=label,
                resend_date=resend_date,
                count=event_count(diagnoses[failure.failure_id], failure.log),
                url=reviewed_url if reviewed_url in RESEND_URLS else None,
            )
            key = label, resend_date
            previous = selected.get(key)
            if previous is None or (candidate.count or 0) > (previous.count or 0):
                selected[key] = candidate
    return tuple(selected[key] for key in sorted(selected))


def _logical_date(failure: AirflowFailure) -> date:
    """Return the Airflow logical date used for a resend action."""
    _, separator, timestamp = failure.run_id.partition("__")
    if separator:
        try:
            return datetime.fromisoformat(timestamp).date()
        except ValueError:
            pass
    return failure.start_at.date()


def _join_terms(values: tuple[str, ...]) -> str:
    """Join labels with natural-language punctuation."""
    if len(values) < PAIR_SIZE:
        return values[0] if values else ""
    if len(values) == PAIR_SIZE:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])}, and {values[-1]}"
