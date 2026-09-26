"""Immutable evidence and finding models for anti-leak analysis."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MountedPath:
    """Describe one recorded container mount."""

    source: str
    destination: str
    read_only: bool


@dataclass(frozen=True, slots=True)
class ContainerEvidence:
    """Recorded container state safe for deterministic benchmark replay."""

    user: str
    read_only_root: bool
    environment: tuple[str, ...]
    mounts: tuple[MountedPath, ...]
    capabilities: tuple[str, ...]
    visible_files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LeakFinding:
    """One evidence-qualified data leak or security weakness."""

    finding_id: str
    severity: str
    evidence: str
    remediation: str
