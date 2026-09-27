"""Render the evidence-rich Developer production-support report."""

from __future__ import annotations

from collections.abc import Iterable

from workspaces.data_engineering.agents.production_support.models import (
    FailureDiagnosis,
    FailureKind,
    Region,
)
from workspaces.data_engineering.agents.production_support.report_findings import (
    ReportFindings,
)
from workspaces.data_engineering.agents.production_support.reporting_details import (
    ClientIdentity,
    FailureGroup,
    client_identities,
    failure_subject,
    group_failures_for_reporting,
    identity_gap,
)
from workspaces.data_engineering.agents.production_support.reporting_health import (
    dag_parsing_line,
    developer_health_line,
    health_by_region,
)

PAIR_SIZE = 2


class DeveloperReporter:
    """Render complete evidence for the engineering audience."""

    def render(
        self,
        findings: ReportFindings,
    ) -> str:
        """Return the Developer report with health findings first."""
        diagnosis_by_id = {item.failure_id: item for item in findings.diagnoses}
        identities = client_identities(findings.resource_discovery_results)
        regional_health = health_by_region(findings.cluster_health, findings.regions)
        lines = [
            "Message for developer:",
            *(
                developer_health_line(regional_health[region])
                for region in findings.regions
            ),
        ]
        parsing_line = (
            dag_parsing_line(regional_health)
            if set(findings.regions) == {Region.US_01, Region.CA_02}
            else None
        )
        if parsing_line is not None:
            lines.append(parsing_line)
        for region in findings.regions:
            regional = tuple(
                item for item in findings.failures if item.region is region
            )
            lines.extend(
                _developer_line(group, diagnosis_by_id, identities)
                for group in group_failures_for_reporting(regional, identities)
            )
        return "\n".join(lines)


def _diagnosis_label(diagnosis: FailureDiagnosis) -> str:
    if diagnosis.kind is FailureKind.UNKNOWN_RESOURCE_TERMINATION:
        return "unknown resource termination without corroborating OOM evidence"
    return diagnosis.kind.value


def _developer_line(
    group: FailureGroup,
    diagnoses: dict[str, FailureDiagnosis],
    identities: dict[str, ClientIdentity],
) -> str:
    classifications = _unique_terms(
        _diagnosis_label(diagnoses[failure.failure_id]) for failure in group.failures
    )
    sources = _unique_terms(
        diagnoses[failure.failure_id].source.value for failure in group.failures
    )
    statuses = _unique_terms(
        diagnoses[failure.failure_id].status.value for failure in group.failures
    )
    gaps = _unique_terms(
        f"{failure_subject(failure, identities)}{gap}"
        for failure in group.failures
        if (gap := identity_gap(failure, identities))
    )
    details = [
        f"classification: {_join_terms(classifications)}",
        _developer_evidence(group, diagnoses, identities),
        f"source: {_join_terms(sources)}",
        f"status: {_join_terms(statuses)}",
    ]
    if gaps:
        details.append(f"identity: {_join_terms(gaps)}")
    return (
        f"  - {_join_terms(group.subject_labels)} failed on "
        f"{_join_terms(group.jobs)}: "
        f"{'; '.join(details)}"
    )


def _first_evidence(diagnosis: FailureDiagnosis) -> str:
    return diagnosis.evidence[0] if diagnosis.evidence else "no terminal evidence"


def _developer_evidence(
    group: FailureGroup,
    diagnoses: dict[str, FailureDiagnosis],
    identities: dict[str, ClientIdentity],
) -> str:
    evidence = _unique_terms(
        _first_evidence(diagnoses[failure.failure_id]) for failure in group.failures
    )
    if len(evidence) == 1:
        return f"evidence: {evidence[0]}"
    qualified = _unique_terms(
        (
            f"{failure_subject(failure, identities)} "
            f"{failure.task_id.split('.', maxsplit=1)[0]}: "
            f"{_first_evidence(diagnoses[failure.failure_id])}"
        )
        for failure in group.failures
    )
    return f"evidence by failure: {'; '.join(qualified)}"


def _join_terms(values: tuple[str, ...]) -> str:
    if len(values) < PAIR_SIZE:
        return "".join(values)
    if len(values) == PAIR_SIZE:
        return " and ".join(values)
    return f"{', '.join(values[:-1])}, and {values[-1]}"


def _unique_terms(values: Iterable[object]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values))
