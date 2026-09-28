"""Concurrency-safe in-memory adapter for agent memory tests and local use."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from uuid import UUID

from agent_memory import (
    EvidenceOutcome,
    MemoryEvidence,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryStatus,
)


class MemoryConflictError(ValueError):
    """Raised when one scoped key is assigned conflicting meanings."""


class MemoryNotFoundError(LookupError):
    """Raised when evidence targets an unavailable memory."""


class InMemoryAgentMemoryStore:
    """Store immutable memory records behind an async lock."""

    def __init__(self) -> None:
        """Initialize an empty store."""
        self._records: dict[UUID, MemoryRecord] = {}
        self._evidence: list[tuple[UUID, EvidenceOutcome, str]] = []
        self._lock = asyncio.Lock()

    async def find(
        self,
        *,
        agent_id: str,
        scope: MemoryScope,
        kind: MemoryKind,
        normalized_key: str,
    ) -> tuple[MemoryRecord, ...]:
        """Return exact active memories in deterministic order."""
        async with self._lock:
            return tuple(
                sorted(
                    (
                        memory
                        for memory in self._records.values()
                        if memory.agent_id == agent_id
                        and memory.scope == scope
                        and memory.kind is kind
                        and memory.normalized_key == normalized_key
                        and memory.status
                        not in {MemoryStatus.REJECTED, MemoryStatus.SUPERSEDED}
                    ),
                    key=lambda memory: str(memory.memory_id),
                )
            )

    async def put(self, memory: MemoryRecord) -> MemoryRecord:
        """Insert one memory while rejecting conflicting scoped keys."""
        async with self._lock:
            existing = next(
                (
                    item
                    for item in self._records.values()
                    if _same_key(item, memory)
                    and item.status
                    not in {MemoryStatus.REJECTED, MemoryStatus.SUPERSEDED}
                ),
                None,
            )
            if existing is not None:
                if existing.metadata != memory.metadata:
                    message = (
                        f"memory key {memory.key!r} already has a different meaning"
                    )
                    raise MemoryConflictError(message)
                return existing
            self._records[memory.memory_id] = memory
            return memory

    async def record_evidence(
        self,
        *,
        agent_id: str,
        scope: MemoryScope,
        evidence: MemoryEvidence,
        promote_after: int,
    ) -> MemoryRecord:
        """Append evidence and update status atomically."""
        async with self._lock:
            memory = self._records.get(evidence.memory_id)
            if memory is None or memory.agent_id != agent_id or memory.scope != scope:
                message = (
                    f"memory {evidence.memory_id} was not found in the requested scope"
                )
                raise MemoryNotFoundError(message)
            prior = next(
                (
                    item
                    for item in self._evidence
                    if item[0] == evidence.memory_id
                    and item[2] == evidence.correlation_id
                ),
                None,
            )
            if prior is not None:
                if prior[1] is not evidence.outcome:
                    message = (
                        f"correlation {evidence.correlation_id!r} "
                        "already recorded different evidence"
                    )
                    raise MemoryConflictError(message)
                return memory
            if evidence.outcome is EvidenceOutcome.REJECTED:
                updated = replace(memory, status=MemoryStatus.REJECTED)
            else:
                evidence_count = memory.evidence_count + 1
                updated = replace(
                    memory,
                    evidence_count=evidence_count,
                    confidence=min(1.0, evidence_count / promote_after),
                    status=(
                        MemoryStatus.CONFIRMED
                        if evidence_count >= promote_after
                        else MemoryStatus.PROPOSED
                    ),
                )
            self._records[evidence.memory_id] = updated
            self._evidence.append(
                (
                    evidence.memory_id,
                    evidence.outcome,
                    evidence.correlation_id,
                )
            )
            return updated


def _same_key(left: MemoryRecord, right: MemoryRecord) -> bool:
    return (
        left.agent_id == right.agent_id
        and left.scope == right.scope
        and left.kind is right.kind
        and left.normalized_key == right.normalized_key
    )
