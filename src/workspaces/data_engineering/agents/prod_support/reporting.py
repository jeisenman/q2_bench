"""Format production-support findings."""

from __future__ import annotations

from datetime import date

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
