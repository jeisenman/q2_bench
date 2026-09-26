"""Framework-neutral anti-leak agent with an intentionally weak v1."""

from __future__ import annotations

from domain import AgentDefinition, AgentRequest, AgentResult, ToolDefinition
from workspaces.data_engineering.agents.anti_leak.ports import (
    AntiLeakEvidenceSource,
)
from workspaces.data_engineering.agents.anti_leak.reporting import render_findings
from workspaces.data_engineering.agents.anti_leak.scanner import scan_v1

ANTI_LEAK_V1_DEFINITION = AgentDefinition(
    name="anti-leak",
    description="Audit recorded container evidence for leaks and weak isolation.",
    instructions=(
        "Version one is an intentionally incomplete baseline. Inspect only the "
        "provided sanitized snapshot. Report root execution and visible .env "
        "files. Never inspect the host or expose credential values."
    ),
    tools=(
        ToolDefinition(
            name="load_container_evidence",
            description="Load a sanitized, deterministic container snapshot.",
        ),
    ),
    version="1",
)


class AntiLeakAgent:
    """Analyze sanitized container evidence without host filesystem access."""

    def __init__(self, evidence_source: AntiLeakEvidenceSource) -> None:
        """Create the v1 agent with an injected replay or production source."""
        self._evidence_source = evidence_source

    @property
    def definition(self) -> AgentDefinition:
        """Return the intentionally weak version-one definition."""
        return ANTI_LEAK_V1_DEFINITION

    async def run(self, request: AgentRequest) -> AgentResult:
        """Load evidence, run the v1 scanner, and return its incomplete report."""
        evidence = self._evidence_source.load()
        findings = scan_v1(evidence)
        return AgentResult(
            output=render_findings(findings),
            correlation_id=request.correlation_id,
            tool_calls=("load_container_evidence",),
            attributes=(
                ("agent_version", "1"),
                ("finding_count", len(findings)),
                ("known_incomplete", True),
            ),
        )
