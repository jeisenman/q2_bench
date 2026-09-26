"""Render deterministic anti-leak findings."""

from workspaces.data_engineering.agents.anti_leak.models import LeakFinding


def render_findings(findings: tuple[LeakFinding, ...]) -> str:
    """Render a concise security report."""
    lines = ["# Anti-leak container review", "", "Version: v1-intentionally-bad", ""]
    if not findings:
        return "\n".join((*lines, "No leaks detected."))
    lines.append("Findings:")
    lines.extend(
        f"- [{finding.severity}] {finding.finding_id}: {finding.evidence} "
        f"Remediation: {finding.remediation}"
        for finding in findings
    )
    return "\n".join(lines)
