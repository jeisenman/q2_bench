"""Render approval-gated production-support follow-up actions."""

from __future__ import annotations

from datetime import date

from workspaces.data_engineering.agents.prod_support.report_findings import (
    ReportFindings,
)
from workspaces.data_engineering.agents.prod_support.reporting_details import (
    client_identities,
    format_follow_up,
)


class FollowUp:
    """Render read-only remediation choices without executing them."""

    def render(
        self,
        operational_date: date,
        findings: ReportFindings,
    ) -> str:
        """Return actionable resend and approval-gated rerun choices."""
        return format_follow_up(
            operational_date,
            findings.failures,
            {item.failure_id: item for item in findings.diagnoses},
            client_identities(findings.resource_discovery_results),
            findings.config,
        )
