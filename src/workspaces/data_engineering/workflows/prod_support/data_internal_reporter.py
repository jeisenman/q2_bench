"""Render the concise Data Internal production-support report."""

from __future__ import annotations

from datetime import date

from workspaces.data_engineering.workflows.prod_support.models import (
    Region,
)
from workspaces.data_engineering.workflows.prod_support.report_findings import (
    ReportFindings,
)
from workspaces.data_engineering.workflows.prod_support.reporting_channel import (
    data_internal_lines,
)
from workspaces.data_engineering.workflows.prod_support.reporting_details import (
    client_identities,
    group_failures_for_reporting,
    include_in_data_internal,
)


class DataInternalReporter:
    """Render audience-filtered regional operational findings."""

    def render(
        self,
        operational_date: date,
        findings: ReportFindings,
    ) -> str:
        """Return the compact Data Internal report without periods."""
        diagnosis_by_id = {item.failure_id: item for item in findings.diagnoses}
        identities = client_identities(findings.resource_discovery_results)
        lines = [f":bangbang: PROD SUPPORT {operational_date.isoformat()} :bangbang:"]
        for index, region in enumerate(findings.regions):
            if index:
                lines.append("")
            label = "US" if region is Region.US_01 else "CA"
            all_regional = tuple(
                item for item in findings.failures if item.region is region
            )
            regional = tuple(
                item
                for item in all_regional
                if include_in_data_internal(item, findings.config)
            )
            lines.append(label)
            lines.append("- Ongoing" if regional else "- Good")
            lines.extend(
                line
                for group in group_failures_for_reporting(regional, identities)
                for line in data_internal_lines(
                    group,
                    diagnosis_by_id,
                    identities,
                )
            )
        return "\n".join(lines).replace(".", "")
