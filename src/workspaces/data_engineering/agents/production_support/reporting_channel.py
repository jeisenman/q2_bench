"""Render concise Data Internal failure groups."""

from __future__ import annotations

from workspaces.data_engineering.agents.production_support.models import (
    FailureDiagnosis,
    FailureKind,
)
from workspaces.data_engineering.agents.production_support.reporting_details import (
    ClientIdentity,
    FailureGroup,
    event_count,
    failure_subject,
    is_resend_failure,
    job_label,
)

MAX_BULLET_CHARACTERS = 180
LARGE_RESEND_THRESHOLD = 100
PAIR_SIZE = 2


def data_internal_lines(
    group: FailureGroup,
    diagnoses: dict[str, FailureDiagnosis],
    identities: dict[str, ClientIdentity],
) -> tuple[str, ...]:
    """Render a group, splitting only when the compact line exceeds its budget."""
    if len(_render_line(group, diagnoses, identities)) <= MAX_BULLET_CHARACTERS:
        return (_render_line(group, diagnoses, identities),)
    chunks = _split_group(group, diagnoses, identities)
    return tuple(_render_line(chunk, diagnoses, identities) for chunk in chunks)


def _render_line(
    group: FailureGroup,
    diagnoses: dict[str, FailureDiagnosis],
    identities: dict[str, ClientIdentity],
) -> str:
    line = (
        f"  - {_join_terms(group.subject_labels)} failed on {_join_terms(group.jobs)}"
    )
    salient = tuple(
        dict.fromkeys(
            label
            for failure in group.failures
            if (label := _salient_diagnosis(diagnoses[failure.failure_id]))
        )
    )
    large_resend = _large_resend_label(group, diagnoses, identities)
    if large_resend is not None:
        salient = (*salient, large_resend)
    return f"{line} with {_join_terms(salient)}" if salient else line


def _split_group(
    group: FailureGroup,
    diagnoses: dict[str, FailureDiagnosis],
    identities: dict[str, ClientIdentity],
) -> tuple[FailureGroup, ...]:
    if len(group.subject_labels) > 1:
        candidates = tuple(
            FailureGroup(
                (subject,),
                group.jobs,
                tuple(
                    failure
                    for failure in group.failures
                    if failure_subject(failure, identities) == subject
                ),
            )
            for subject in group.subject_labels
        )
    elif len(group.jobs) > 1:
        candidates = tuple(
            FailureGroup(
                group.subject_labels,
                (job,),
                tuple(
                    failure
                    for failure in group.failures
                    if job_label(failure.task_id) == job
                ),
            )
            for job in group.jobs
        )
    else:
        return (group,)
    return _merge_within_budget(candidates, diagnoses, identities)


def _merge_within_budget(
    candidates: tuple[FailureGroup, ...],
    diagnoses: dict[str, FailureDiagnosis],
    identities: dict[str, ClientIdentity],
) -> tuple[FailureGroup, ...]:
    chunks: list[FailureGroup] = []
    current: FailureGroup | None = None
    for candidate in candidates:
        combined = candidate if current is None else _combine(current, candidate)
        if (
            current is not None
            and len(_render_line(combined, diagnoses, identities))
            > MAX_BULLET_CHARACTERS
        ):
            chunks.append(current)
            current = candidate
        else:
            current = combined
    if current is not None:
        chunks.append(current)
    return tuple(chunks)


def _combine(left: FailureGroup, right: FailureGroup) -> FailureGroup:
    return FailureGroup(
        tuple(dict.fromkeys((*left.subject_labels, *right.subject_labels))),
        tuple(dict.fromkeys((*left.jobs, *right.jobs))),
        (*left.failures, *right.failures),
    )


def _large_resend_label(
    group: FailureGroup,
    diagnoses: dict[str, FailureDiagnosis],
    identities: dict[str, ClientIdentity],
) -> str | None:
    large: list[tuple[str, int]] = []
    for failure in group.failures:
        if not is_resend_failure(failure):
            continue
        count = event_count(diagnoses[failure.failure_id], failure.log)
        if count is not None and count > LARGE_RESEND_THRESHOLD:
            large.append((failure_subject(failure, identities), count))
    if not large:
        return None
    notices = tuple(
        f"{count:,} events for {subject}" for subject, count in dict(large).items()
    )
    return f"{_join_terms(notices)} requiring pd-rix follow-up"


def _salient_diagnosis(diagnosis: FailureDiagnosis) -> str | None:
    labels = {
        FailureKind.DISTINCTNESS: "distinctness validation errors",
        FailureKind.OMS_CONFIRMED_TIMEOUT: "timeout",
        FailureKind.AIRFLOW_CONFIRMED_TIMEOUT: "timeout",
        FailureKind.CONFIRMED_OOM: "OOM",
        FailureKind.PROBABLE_OOM: "probable OOM",
    }
    return labels.get(diagnosis.kind)


def _join_terms(values: tuple[str, ...]) -> str:
    if len(values) < PAIR_SIZE:
        return "".join(values)
    if len(values) == PAIR_SIZE:
        return " and ".join(values)
    return f"{', '.join(values[:-1])}, and {values[-1]}"
