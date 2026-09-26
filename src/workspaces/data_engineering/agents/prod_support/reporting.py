"""Format production-support findings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from urllib.parse import urlencode

from domain import AgentResult
from workspaces.data_engineering.agents.prod_support.models import (
    AirflowFailure,
    FailureDiagnosis,
    FailureKind,
    Region,
)

HISTORICAL_WINDOW_DAYS = 2
TICKET_ATTEMPT_THRESHOLD = 5


@dataclass(frozen=True, slots=True)
class ProdSupportReports:
    """Channel-specific reports and the suggestion-only follow-up."""

    developer: str
    data_internal: str
    follow_up: str

    @property
    def combined(self) -> str:
        """Return the backward-compatible combined report."""
        return "\n\n".join((self.developer, self.data_internal))


def format_report(
    operational_date: date,
    failures: tuple[AirflowFailure, ...],
    diagnoses: tuple[FailureDiagnosis, ...],
    *,
    reference_date: date | None = None,
) -> str:
    """Render a deterministic regional production-support report."""
    return format_reports(
        operational_date,
        failures,
        diagnoses,
        reference_date=reference_date,
    ).combined


def format_reports(
    operational_date: date,
    failures: tuple[AirflowFailure, ...],
    diagnoses: tuple[FailureDiagnosis, ...],
    *,
    reference_date: date | None = None,
    resource_discovery_results: tuple[AgentResult, ...] = (),
) -> ProdSupportReports:
    """Render channel-specific reports and a read-only follow-up."""
    diagnosis_by_id = {item.failure_id: item for item in diagnoses}
    developer_lines = [
        "Message for Developer",
        (
            "- US Cluster failures: "
            f"{airflow_failure_url(Region.US_01, operational_date, reference_date)}"
        ),
        (
            "- CA Cluster failures: "
            f"{airflow_failure_url(Region.CA_02, operational_date, reference_date)}"
        ),
        (
            "- Terminology: DV means Distinctness Validation. "
            "MI means Market Insights; MI3 means Market Insights 3."
        ),
    ]
    for failure in failures:
        diagnosis = diagnosis_by_id[failure.failure_id]
        evidence = (
            diagnosis.evidence[0] if diagnosis.evidence else "no terminal evidence"
        )
        developer_lines.append(
            f"- {failure.region.value} {failure.dag_id} / {failure.task_id}: "
            f"{_diagnosis_label(diagnosis)}; evidence: {evidence}"
        )
    if resource_discovery_results:
        developer_lines.append("- Resource Discovery:")
        developer_lines.extend(
            f"  - {result.output.replace(chr(10), '; ')}"
            for result in resource_discovery_results
        )
    data_internal_lines = [
        "Message for Data Internal Channel",
        f":bangbang: PROD SUPPORT {operational_date.isoformat()} :bangbang:",
        "",
    ]
    for region, label in ((Region.US_01, "US"), (Region.CA_02, "CA")):
        regional = tuple(item for item in failures if item.region is region)
        data_internal_lines.append(label)
        data_internal_lines.append("- Good" if not regional else "- Ongoing")
        for failure in regional:
            diagnosis = diagnosis_by_id[failure.failure_id]
            ticket = (
                " -- making ticket to fix"
                if failure.try_number > TICKET_ATTEMPT_THRESHOLD
                else ""
            )
            data_internal_lines.append(
                f"  - {failure.dag_id} / {failure.task_id}: "
                f"{_diagnosis_label(diagnosis)}{ticket}"
            )
    follow_up = _format_follow_up(failures)
    return ProdSupportReports(
        developer="\n".join(developer_lines),
        data_internal="\n".join(data_internal_lines),
        follow_up=follow_up,
    )


def _format_follow_up(failures: tuple[AirflowFailure, ...]) -> str:
    if not failures:
        return "No Airflow task retries are suggested for this operational window."
    lines = ["Would you like me to prepare retry recommendations for:"]
    lines.extend(
        f"- {failure.region.value} {failure.dag_id} / {failure.task_id} "
        f"(attempt {failure.try_number})?"
        for failure in failures
    )
    return "\n".join(lines)


def _diagnosis_label(diagnosis: FailureDiagnosis) -> str:
    if diagnosis.kind is FailureKind.UNKNOWN_RESOURCE_TERMINATION:
        return "unknown_resource_termination: likely OOMed"
    return diagnosis.kind.value


def airflow_failure_url(
    region: Region,
    operational_date: date,
    reference_date: date | None = None,
) -> str:
    """Return the filtered Airflow task-instance URL for one region and day."""
    host = {
        Region.US_01: "airflow-us01.precisionlender.com",
        Region.CA_02: "airflow-ca02.precisionlender.com",
    }[region]
    cutoff = datetime.combine(operational_date, time(hour=9), tzinfo=UTC)
    filters = {"_flt_1_end_date": cutoff.isoformat()}
    if (
        reference_date is not None
        and (reference_date - operational_date).days >= HISTORICAL_WINDOW_DAYS
    ):
        upper_bound = cutoff + timedelta(days=1)
        filters["_flt_2_end_date"] = upper_bound.isoformat()
    filters["_flt_3_state"] = "failed"
    query = urlencode(filters)
    return f"https://{host}/taskinstance/list/?{query}#"
