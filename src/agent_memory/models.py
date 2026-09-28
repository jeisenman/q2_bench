"""Immutable models shared by agent memory services and storage adapters."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

MEMORY_KEY_CHARACTERS = re.compile(r"[^a-z0-9]+")


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        message = f"{field_name} must not be empty"
        raise ValueError(message)


def normalize_memory_key(value: str) -> str:
    """Return a stable punctuation-insensitive memory lookup key."""
    _require_text(value, "memory key")
    return MEMORY_KEY_CHARACTERS.sub(" ", value.casefold()).strip()


class MemoryScopeType(StrEnum):
    """Supported memory visibility boundaries."""

    USER = "user"
    TEAM = "team"
    ORGANIZATION = "organization"


class MemoryKind(StrEnum):
    """Supported durable memory categories."""

    ALIAS = "alias"
    FACT = "fact"
    PREFERENCE = "preference"
    SUMMARY = "summary"


class MemoryStatus(StrEnum):
    """Lifecycle state of a durable memory."""

    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class EvidenceOutcome(StrEnum):
    """User feedback applied to a memory."""

    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class AliasResolutionStatus(StrEnum):
    """Outcome of an exact alias-memory lookup."""

    NOT_FOUND = "not_found"
    CONFIRMATION_REQUIRED = "confirmation_required"
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class MemoryScope:
    """Identify the tenant and audience allowed to retrieve a memory."""

    tenant_id: str
    scope_type: MemoryScopeType
    scope_id: str

    def __post_init__(self) -> None:
        """Validate all isolation fields."""
        _require_text(self.tenant_id, "tenant_id")
        _require_text(self.scope_id, "scope_id")
        if not isinstance(self.scope_type, MemoryScopeType):
            message = "scope_type must be a MemoryScopeType"
            raise TypeError(message)


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    """Represent one bounded durable memory and optional embedding."""

    memory_id: UUID
    agent_id: str
    scope: MemoryScope
    kind: MemoryKind
    key: str
    content: str
    status: MemoryStatus = MemoryStatus.PROPOSED
    confidence: float = 0.0
    evidence_count: int = 0
    metadata: tuple[tuple[str, str], ...] = ()
    embedding: tuple[float, ...] = ()
    embedding_model: str | None = None

    def __post_init__(self) -> None:
        """Validate bounded content, confidence, metadata, and vectors."""
        _require_text(self.agent_id, "agent_id")
        _require_text(self.key, "key")
        _require_text(self.content, "content")
        if not isinstance(self.kind, MemoryKind):
            message = "kind must be a MemoryKind"
            raise TypeError(message)
        if not isinstance(self.status, MemoryStatus):
            message = "status must be a MemoryStatus"
            raise TypeError(message)
        if not 0.0 <= self.confidence <= 1.0:
            message = "confidence must be between 0 and 1"
            raise ValueError(message)
        if self.evidence_count < 0:
            message = "evidence_count must not be negative"
            raise ValueError(message)
        names = tuple(name for name, _ in self.metadata)
        if len(names) != len(set(names)):
            message = "memory metadata keys must be unique"
            raise ValueError(message)
        if any(not math.isfinite(value) for value in self.embedding):
            message = "memory embedding values must be finite"
            raise ValueError(message)
        if self.embedding and not self.embedding_model:
            message = "embedding_model is required when embedding is present"
            raise ValueError(message)

    @property
    def normalized_key(self) -> str:
        """Return the stable lookup key."""
        return normalize_memory_key(self.key)

    @property
    def metadata_mapping(self) -> Mapping[str, str]:
        """Return immutable typed metadata."""
        return MappingProxyType(dict(self.metadata))


@dataclass(frozen=True, slots=True)
class MemoryEvidence:
    """Record one explicit feedback event for a durable memory."""

    memory_id: UUID
    outcome: EvidenceOutcome
    correlation_id: str

    def __post_init__(self) -> None:
        """Validate feedback identity and provenance."""
        if not isinstance(self.outcome, EvidenceOutcome):
            message = "outcome must be an EvidenceOutcome"
            raise TypeError(message)
        _require_text(self.correlation_id, "correlation_id")


@dataclass(frozen=True, slots=True)
class AliasResolution:
    """Return exact alias memories and their deterministic resolution state."""

    status: AliasResolutionStatus
    matches: tuple[MemoryRecord, ...] = ()

    @property
    def unique(self) -> MemoryRecord | None:
        """Return the sole memory when cardinality is unique."""
        return self.matches[0] if len(self.matches) == 1 else None
