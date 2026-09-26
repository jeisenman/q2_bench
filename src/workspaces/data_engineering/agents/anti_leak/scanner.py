"""Intentionally incomplete version-one anti-leak scanner."""

from __future__ import annotations

from workspaces.data_engineering.agents.anti_leak.models import (
    ContainerEvidence,
    LeakFinding,
)


def scan_v1(evidence: ContainerEvidence) -> tuple[LeakFinding, ...]:
    """Run the deliberately shallow baseline checks used by version one."""
    findings: list[LeakFinding] = []
    if evidence.user == "root":
        findings.append(
            LeakFinding(
                finding_id="root-user",
                severity="high",
                evidence="Container process runs as root.",
                remediation="Run with a dedicated non-root UID and GID.",
            )
        )
    leaked_env_files = tuple(
        path for path in evidence.visible_files if path.endswith("/.env")
    )
    if leaked_env_files:
        findings.append(
            LeakFinding(
                finding_id="visible-dotenv",
                severity="high",
                evidence=f"Visible dotenv files: {', '.join(leaked_env_files)}",
                remediation="Remove dotenv files from the image and build context.",
            )
        )
    return tuple(findings)
