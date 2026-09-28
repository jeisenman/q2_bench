"""Storage ports for durable agent memory."""

from typing import Protocol

from agent_memory.models import (
    MemoryEvidence,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
)


class AgentMemoryStore(Protocol):
    """Persist and retrieve bounded memories independently of PostgreSQL."""

    async def find(
        self,
        *,
        agent_id: str,
        scope: MemoryScope,
        kind: MemoryKind,
        normalized_key: str,
    ) -> tuple[MemoryRecord, ...]:
        """Return active exact-key memories in deterministic order."""
        ...

    async def put(self, memory: MemoryRecord) -> MemoryRecord:
        """Persist a new memory or return the identical existing memory."""
        ...

    async def record_evidence(
        self,
        *,
        agent_id: str,
        scope: MemoryScope,
        evidence: MemoryEvidence,
        promote_after: int,
    ) -> MemoryRecord:
        """Record feedback and atomically update the memory lifecycle."""
        ...
