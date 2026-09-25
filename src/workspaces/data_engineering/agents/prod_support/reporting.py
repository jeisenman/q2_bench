"""Format production-support findings."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from urllib.parse import urlencode

from workspaces.data_engineering.agents.prod_support.models import (
    AirflowFailure,
    FailureDiagnosis,
    Region,
)


def format_report(
    operational_date: date,
    failures: tuple[AirflowFailure, ...],
    diagnoses: tuple[FailureDiagnosis, ...],
) -> str:
    """Render a deterministic regional production-support report."""
    diagnosis_by_id = {item.failure_id: item for item in diagnoses}
    lines = [
        "URLs to validate",
        f"- {airflow_failure_url(Region.US_01, operational_date)}",
        f"- {airflow_failure_url(Region.CA_02, operational_date)}",
        "",
        "Message for Data Internal Channel",
        f":bangbang: PROD SUPPORT {operational_date.isoformat()} :bangbang:",
    ]
    for region, label in ((Region.US_01, "US"), (Region.CA_02, "CA")):
        regional = tuple(item for item in failures if item.region is region)
        lines.append(label)
        lines.append("- Good" if not regional else "- Ongoing")
        for failure in regional:
            diagnosis = diagnosis_by_id[failure.failure_id]
            lines.append(
                f"  - {failure.dag_id} / {failure.task_id}: {diagnosis.kind.value}"
            )
    return "\n".join(lines)


def airflow_failure_url(region: Region, operational_date: date) -> str:
    """Return the filtered Airflow task-instance URL for one region and day."""
    host = {
        Region.US_01: "airflow-us01.precisionlender.com",
        Region.CA_02: "airflow-ca02.precisionlender.com",
    }[region]
    cutoff = datetime.combine(operational_date, time(hour=5), tzinfo=UTC)
    query = urlencode(
        {
            "_flt_3_state": "failed",
            "_flt_2_end_date": cutoff.strftime("%m/%d/%Y %-I:%M %p"),
        }
    )
    return f"https://{host}/taskinstance/list/?{query}#"
