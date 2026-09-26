"""Typed evidence boundary for anti-leak agents."""

from __future__ import annotations

from typing import Protocol

from workspaces.data_engineering.agents.anti_leak.models import ContainerEvidence


class AntiLeakEvidenceSource(Protocol):
    """Load one recorded container snapshot without inspecting the host."""

    def load(self) -> ContainerEvidence:
        """Return deterministic, sanitized container evidence."""
        ...
