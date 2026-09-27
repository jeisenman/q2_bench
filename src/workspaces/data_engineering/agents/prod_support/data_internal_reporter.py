"""Render the concise Data Internal production-support report."""

from __future__ import annotations

from datetime import date

from workspaces.data_engineering.agents.prod_support.cluster_health import (
    ClusterHealthState,
)
from workspaces.data_engineering.agents.prod_support.models import (
    Region,
)
from workspaces.data_engineering.agents.prod_support.report_findings import (
    ReportFindings,
)
from workspaces.data_engineering.agents.prod_support.reporting_channel import (
    data_internal_lines,
)
from workspaces.data_engineering.agents.prod_support.reporting_details import (
    client_identities,
    group_failures_for_reporting,
    include_in_data_internal,
)
from workspaces.data_engineering.agents.prod_support.reporting_health import (
    data_internal_health_line,
    health_by_region,
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
        regional_health = health_by_region(findings.cluster_health, findings.regions)
        lines = [f":bangbang: PROD SUPPORT {operational_date.isoformat()} :bangbang:"]
        for region in findings.regions:
            label = "US" if region is Region.US_01 else "CA"
            all_regional = tuple(
                item for item in findings.failures if item.region is region
            )
            regional = tuple(
                item
                for item in all_regional
                if include_in_data_internal(item, findings.config)
            )
            health = regional_health[region]
            ongoing = bool(all_regional) or health.state is ClusterHealthState.UNHEALTHY
            lines.append(label)
            lines.append("- Ongoing" if ongoing else "- Good")
            if health.state is ClusterHealthState.UNHEALTHY:
                lines.append(data_internal_health_line(health))
            lines.extend(
                line
                for group in group_failures_for_reporting(regional, identities)
                for line in data_internal_lines(
                    group,
                    diagnosis_by_id,
                    identities,
                )
            )
            omission_codes = findings.config.omission_codes(all_regional)
            if omission_codes:
                lines.append(f"  - {', '.join(omission_codes)}")
        return "\n".join(lines).replace(".", "")
