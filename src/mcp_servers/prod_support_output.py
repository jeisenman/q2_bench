"""Canonical output helpers for the production-support MCP server."""

from __future__ import annotations

from workspaces.data_engineering.agents.production_support.models import (
    ProdSupportOutcome,
    RetryCandidate,
)


def validation_urls(report: str) -> tuple[str, ...]:
    """Extract standalone Airflow validation URLs from a canonical report."""
    return tuple(
        url
        for line in report.splitlines()
        if (url := _url_from_report_line(line)) is not None
    )


def _url_from_report_line(line: str) -> str | None:
    if not line.startswith("https://airflow-"):
        return None
    return line.strip()


def format_mcp_output(outcome: ProdSupportOutcome) -> str:
    """Return the canonical report without competing formatting."""
    return outcome.report


def retry_approval_message(candidates: tuple[RetryCandidate, ...]) -> str:
    """Return the generic approval prompt for eligible exact reruns."""
    if not candidates:
        return "No re-runs require approval."
    return "\n".join(
        (
            "Do you approve these re-runs?",
            *(f"- {candidate.label}" for candidate in candidates),
        )
    )
