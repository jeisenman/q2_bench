"""Deterministic policy for exact agent-memory aliases."""

from __future__ import annotations

from uuid import UUID, uuid4

from agent_memory.models import (
    AliasResolution,
    AliasResolutionStatus,
    EvidenceOutcome,
    MemoryEvidence,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryStatus,
    normalize_memory_key,
)
from agent_memory.ports import AgentMemoryStore
from observability import traced_operation

DEFAULT_ALIAS_CONFIRMATIONS = 3


class AgentMemory:
    """Manage one agent's durable memories within an explicit scope."""

    def __init__(
        self,
        store: AgentMemoryStore,
        *,
        agent_id: str,
        scope: MemoryScope,
        alias_confirmations: int = DEFAULT_ALIAS_CONFIRMATIONS,
    ) -> None:
        """Initialize scoped memory with a deterministic promotion threshold."""
        if not agent_id.strip():
            message = "agent_id must not be empty"
            raise ValueError(message)
        if alias_confirmations < 1:
            message = "alias_confirmations must be at least 1"
            raise ValueError(message)
        self._store = store
        self.agent_id = agent_id
        self.scope = scope
        self.alias_confirmations = alias_confirmations

    async def resolve_alias(self, alias: str) -> AliasResolution:
        """Resolve an alias without using semantic similarity."""
        async with traced_operation(
            "memory.alias.resolve",
            attributes={"q2.agent.name": self.agent_id},
        ):
            matches = await self._store.find(
                agent_id=self.agent_id,
                scope=self.scope,
                kind=MemoryKind.ALIAS,
                normalized_key=normalize_memory_key(alias),
            )
        active = tuple(
            memory
            for memory in matches
            if memory.status in {MemoryStatus.PROPOSED, MemoryStatus.CONFIRMED}
        )
        if not active:
            status = AliasResolutionStatus.NOT_FOUND
        elif len(active) > 1:
            status = AliasResolutionStatus.AMBIGUOUS
        elif active[0].status is MemoryStatus.CONFIRMED:
            status = AliasResolutionStatus.RESOLVED
        else:
            status = AliasResolutionStatus.CONFIRMATION_REQUIRED
        return AliasResolution(status, active)

    async def propose_alias(
        self,
        *,
        alias: str,
        canonical_entity_type: str,
        canonical_entity_id: str,
        canonical_name: str,
    ) -> MemoryRecord:
        """Store a proposed alias without treating it as authoritative."""
        metadata = (
            ("canonical_entity_id", canonical_entity_id),
            ("canonical_entity_type", canonical_entity_type),
            ("canonical_name", canonical_name),
        )
        async with traced_operation(
            "memory.alias.propose",
            attributes={"q2.agent.name": self.agent_id},
        ):
            return await self._store.put(
                MemoryRecord(
                    memory_id=uuid4(),
                    agent_id=self.agent_id,
                    scope=self.scope,
                    kind=MemoryKind.ALIAS,
                    key=alias,
                    content=f"{alias} refers to {canonical_name}",
                    metadata=metadata,
                )
            )

    async def record_alias_evidence(
        self,
        memory_id: UUID,
        outcome: EvidenceOutcome,
        *,
        correlation_id: str,
    ) -> MemoryRecord:
        """Record explicit alias confirmation or rejection."""
        async with traced_operation(
            "memory.alias.record_evidence",
            attributes={"q2.agent.name": self.agent_id},
        ):
            return await self._store.record_evidence(
                agent_id=self.agent_id,
                scope=self.scope,
                evidence=MemoryEvidence(memory_id, outcome, correlation_id),
                promote_after=self.alias_confirmations,
            )

    async def remember_summary(
        self,
        *,
        key: str,
        content: str,
        metadata: tuple[tuple[str, str], ...] = (),
        confidence: float = 1.0,
    ) -> MemoryRecord:
        """Persist one bounded, evidence-derived summary as confirmed memory."""
        async with traced_operation(
            "memory.summary.remember",
            attributes={"q2.agent.name": self.agent_id},
        ):
            return await self._store.put(
                MemoryRecord(
                    memory_id=uuid4(),
                    agent_id=self.agent_id,
                    scope=self.scope,
                    kind=MemoryKind.SUMMARY,
                    key=key,
                    content=content,
                    status=MemoryStatus.CONFIRMED,
                    confidence=confidence,
                    evidence_count=1,
                    metadata=metadata,
                )
            )
