"""Format production-support findings."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

from domain import AgentResult
from workspaces.data_engineering.agents.prod_support.cluster_health import (
    RegionalClusterHealth,
)
from workspaces.data_engineering.agents.prod_support.data_internal_reporter import (
    DataInternalReporter,
)
from workspaces.data_engineering.agents.prod_support.developer_reporter import (
    DeveloperReporter,
)
from workspaces.data_engineering.agents.prod_support.follow_up import FollowUp
from workspaces.data_engineering.agents.prod_support.models import (
    AirflowFailure,
    FailureDiagnosis,
    Region,
)
from workspaces.data_engineering.agents.prod_support.report_findings import (
    ReportFindings,
)
from workspaces.data_engineering.agents.prod_support.reporting_config import (
    ProdSupportReportConfig,
)


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
                f"Follow Ups:\n\n{self.follow_up}",
            )
        )


@dataclass(frozen=True, slots=True)
class ProdSupportReportContext:
    """Optional identity, audience, and cluster-health inputs."""

    resource_discovery_results: tuple[AgentResult, ...] = ()
    config: ProdSupportReportConfig = field(default_factory=ProdSupportReportConfig)
    cluster_health: tuple[RegionalClusterHealth, ...] = ()
    regions: tuple[Region, ...] = (Region.US_01, Region.CA_02)


def format_report(
    operational_date: date,
    failures: tuple[AirflowFailure, ...],
    diagnoses: tuple[FailureDiagnosis, ...],
    *,
    reference_date: date | None = None,
) -> str:
    """Render a deterministic regional production-support report."""
    del reference_date
    return format_reports(
        operational_date,
        failures,
        diagnoses,
    ).combined


def format_reports(
    operational_date: date,
    failures: tuple[AirflowFailure, ...],
    diagnoses: tuple[FailureDiagnosis, ...],
    *,
    resource_discovery_results: tuple[AgentResult, ...] = (),
    config: ProdSupportReportConfig | None = None,
) -> ProdSupportReports:
    """Render reports through the backward-compatible audience inputs."""
    return format_reports_with_context(
        operational_date,
        failures,
        diagnoses,
        context=ProdSupportReportContext(
            resource_discovery_results=resource_discovery_results,
            config=config or ProdSupportReportConfig(),
        ),
    )


def format_reports_with_context(
    operational_date: date,
    failures: tuple[AirflowFailure, ...],
    diagnoses: tuple[FailureDiagnosis, ...],
    *,
    context: ProdSupportReportContext | None = None,
) -> ProdSupportReports:
    """Render channel-specific reports and a read-only follow-up."""
    report_context = context or ProdSupportReportContext()
    findings = ReportFindings(
        failures=failures,
        diagnoses=diagnoses,
        resource_discovery_results=report_context.resource_discovery_results,
        config=report_context.config,
        cluster_health=report_context.cluster_health,
        regions=report_context.regions,
    )
    urls_to_validate = "\n".join(
        (
            "URLs to validate",
            *(
                airflow_failure_url(region, operational_date)
                for region in report_context.regions
            ),
            *tuple(
                dict.fromkeys(
                    airflow_dag_failure_url(failure, operational_date)
                    for failure in failures
                )
            ),
        )
    )
    developer = DeveloperReporter().render(findings)
    data_internal = DataInternalReporter().render(
        operational_date,
        findings,
    )
    follow_up = FollowUp().render(
        operational_date,
        findings,
    )
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
        developer=developer,
        data_internal=data_internal,
        follow_up=follow_up,
    )


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
        f"?_flt_1_end_date={_iso_utc(end)}"
        "&_flt_3_state=failed"
        f"&_flt_2_end_date={_iso_utc(start)}#"
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
