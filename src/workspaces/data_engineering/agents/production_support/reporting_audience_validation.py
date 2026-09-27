"""Validate audience-specific production-support job visibility."""

from __future__ import annotations

from workspaces.data_engineering.agents.production_support.report_findings import (
    ReportFindings,
)
from workspaces.data_engineering.agents.production_support.reporting_details import (
    job_label,
)


def data_internal_job_violation(
    output: str,
    findings: ReportFindings,
) -> str | None:
    """Return the first omitted or hyphen-rewritten job found in Data Internal."""
    allowed_shorthand = {
        f"  - {', '.join(findings.config.shorthand_codes(regional))}"
        for region in findings.regions
        if (
            regional := tuple(
                failure for failure in findings.failures if failure.region is region
            )
        )
        and findings.config.shorthand_codes(regional)
    }
    lowered = "\n".join(
        line for line in output.splitlines() if line not in allowed_shorthand
    ).casefold()
    for failure in findings.failures:
        group = findings.config.configured_omission_group(failure)
        if group is not None:
            terms = (failure.dag_id, failure.task_id, group.name, group.value)
            violation = next(
                (term for term in terms if term.casefold() in lowered),
                None,
            )
            if violation is not None:
                return violation
            continue
        label = job_label(failure.task_id)
        rewritten = label.replace("_", "-")
        if "_" in label and rewritten.casefold() in lowered:
            return rewritten
    return None
