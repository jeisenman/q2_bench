"""Format production-support findings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from domain import AgentResult
from workspaces.data_engineering.agents.prod_support.models import (
    AirflowFailure,
    FailureDiagnosis,
    FailureKind,
    Region,
)

TICKET_ATTEMPT_THRESHOLD = 5


@dataclass(frozen=True, slots=True)
class ProdSupportReports:
    """Channel-specific reports and the suggestion-only follow-up."""

    heading: str
    window: str
    capture_summary: str
    urls_to_validate: str
    developer: str
    data_internal: str
    follow_up: str

    @property
    def combined(self) -> str:
        """Return the backward-compatible combined report."""
        return "\n\n".join(
            (
                self.heading,
                self.window,
                self.capture_summary,
                self.urls_to_validate,
                self.developer,
                self.data_internal,
            )
        )


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
    urls_to_validate = "\n".join(
        (
            "URLs to validate",
            airflow_failure_url(Region.US_01, operational_date, reference_date),
            airflow_failure_url(Region.CA_02, operational_date, reference_date),
        )
    )
    developer_lines = ["Message for developer:"]
    for failure in failures:
        diagnosis = diagnosis_by_id[failure.failure_id]
        evidence = (
            diagnosis.evidence[0] if diagnosis.evidence else "no terminal evidence"
        )
        developer_lines.append(
            f"  - {failure.region.value} {failure.dag_id} / {failure.task_id}: "
            f"{_diagnosis_label(diagnosis)}; evidence: {evidence}; "
            f"link: {airflow_dag_failure_url(failure, operational_date)}"
        )
    if resource_discovery_results:
        developer_lines.extend(
            f"  - Resource Discovery: {result.output.replace(chr(10), '; ')}"
            for result in resource_discovery_results
        )
    data_internal_lines = [
        "Message for Data Internal Channel",
        f":bangbang: PROD SUPPORT {operational_date.isoformat()} :bangbang:",
    ]
    for region, label in ((Region.US_01, "US"), (Region.CA_02, "CA")):
        regional = tuple(item for item in failures if item.region is region)
        data_internal_lines.append(label)
        data_internal_lines.append("- Good" if not regional else "- Ongoing")
        for dag_id, dag_failures in _group_failures_by_dag(regional):
            findings = "; ".join(
                f"{failure.task_id}: "
                f"{_diagnosis_label(diagnosis_by_id[failure.failure_id])}"
                for failure in dag_failures
            )
            ticket = (
                " -- making ticket to fix"
                if any(
                    failure.try_number > TICKET_ATTEMPT_THRESHOLD
                    for failure in dag_failures
                )
                else ""
            )
            data_internal_lines.append(f"  - {dag_id} failed on {findings}{ticket}")
    follow_up = _format_follow_up(failures)
    operational_start, operational_end = _operational_bounds(operational_date)
    return ProdSupportReports(
        heading=(
            f"# Prod Support Report — {operational_date.isoformat()} operational day"
        ),
        window=(
            f"Window: `{_display_utc(operational_start)}` through "
            f"`{_display_utc(operational_end)}`"
        ),
        capture_summary=_capture_summary(failures),
        urls_to_validate=urls_to_validate,
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
    del reference_date
    host = {
        Region.US_01: "airflow-us01.precisionlender.com",
        Region.CA_02: "airflow-ca02.precisionlender.com",
    }[region]
    start, end = _operational_bounds(operational_date)
    return (
        f"https://{host}/taskinstance/list/"
        f"?_flt_1_start_date={_iso_utc(start)}"
        "&_flt_3_state=failed"
        f"&_flt_2_start_date={_iso_utc(end)}#"
    )


def airflow_dag_failure_url(
    failure: AirflowFailure,
    operational_date: date,
) -> str:
    """Return a bounded failed-run grid link for one Airflow DAG."""
    host = {
        Region.US_01: "airflow-us01.precisionlender.com",
        Region.CA_02: "airflow-ca02.precisionlender.com",
    }[failure.region]
    start, end = _operational_bounds(operational_date)
    return (
        f"https://{host}/dags/{failure.dag_id}/grid"
        "?status=failed"
        f"&execution_start={_iso_utc(start)}"
        f"&execution_end={_iso_utc(end)}"
    )


def _operational_bounds(operational_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(operational_date, time(hour=5), tzinfo=UTC)
    return start, start + timedelta(days=1)


def _iso_utc(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _display_utc(value: datetime) -> str:
    return f"{value:%Y-%m-%d %H:%M:%S} UTC"


def _capture_summary(failures: tuple[AirflowFailure, ...]) -> str:
    counts = {
        region: sum(failure.region is region for failure in failures)
        for region in (Region.US_01, Region.CA_02)
    }
    total = len(failures)
    failure_label = "failure" if total == 1 else "failures"
    if counts[Region.US_01] == total and counts[Region.CA_02] == 0:
        return (
            f"Local capture contains {total} {failure_label}, all from US-01; "
            "no CA failures were recorded."
        )
    if counts[Region.CA_02] == total and counts[Region.US_01] == 0:
        return (
            f"Local capture contains {total} {failure_label}, all from CA-02; "
            "no US failures were recorded."
        )
    return (
        f"Local capture contains {total} {failure_label}: "
        f"{counts[Region.US_01]} from US-01 and "
        f"{counts[Region.CA_02]} from CA-02."
    )


def _group_failures_by_dag(
    failures: tuple[AirflowFailure, ...],
) -> tuple[tuple[str, tuple[AirflowFailure, ...]], ...]:
    grouped: dict[str, list[AirflowFailure]] = {}
    for failure in failures:
        grouped.setdefault(failure.dag_id, []).append(failure)
    return tuple(
        (dag_id, tuple(dag_failures)) for dag_id, dag_failures in grouped.items()
    )
