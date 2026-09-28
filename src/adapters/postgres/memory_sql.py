"""Typed SQL helpers for the PostgreSQL agent-memory adapter."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, TypeAlias
from uuid import UUID

from psycopg import AsyncCursor
from psycopg.types.json import Jsonb

from adapters.postgres.errors import PostgresMemoryError
from agent_memory import (
    EvidenceOutcome,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryScopeType,
    MemoryStatus,
)

MemoryCursor: TypeAlias = AsyncCursor[dict[str, Any]]
MEMORY_COLUMNS = """
    m.memory_id, m.agent_id, m.tenant_id, m.scope_type, m.scope_id,
    m.kind, m.memory_key, m.content, m.status, m.confidence,
    m.evidence_count, m.metadata, m.embedding::text AS embedding,
    m.embedding_model,
    a.canonical_entity_type, a.canonical_entity_id, a.canonical_name
"""


async def set_tenant(cursor: MemoryCursor, scope: MemoryScope) -> None:
    """Set the transaction-local tenant used by row-level security."""
    await cursor.execute(
        "SELECT set_config('app.tenant_id', %s, true)",
        (scope.tenant_id,),
    )


def insert_values(memory: MemoryRecord) -> tuple[object, ...]:
    """Return parameterized values for one bounded memory insert."""
    vector = (
        "[" + ",".join(str(value) for value in memory.embedding) + "]"
        if memory.embedding
        else None
    )
    return (
        memory.memory_id,
        memory.agent_id,
        memory.scope.tenant_id,
        memory.scope.scope_type.value,
        memory.scope.scope_id,
        memory.kind.value,
        memory.key,
        memory.normalized_key,
        memory.content,
        memory.status.value,
        memory.confidence,
        memory.evidence_count,
        Jsonb(dict(memory.metadata)),
        vector,
        memory.embedding_model,
    )


async def insert_alias(cursor: MemoryCursor, memory: MemoryRecord) -> None:
    """Persist typed alias fields for an alias memory."""
    if memory.kind is not MemoryKind.ALIAS:
        return
    metadata = memory.metadata_mapping
    required = (
        "canonical_entity_type",
        "canonical_entity_id",
        "canonical_name",
    )
    if any(not metadata.get(name) for name in required):
        message = "alias memory requires canonical entity metadata"
        raise PostgresMemoryError(message)
    await cursor.execute(
        """
        INSERT INTO memory.aliases (
            memory_id, tenant_id, canonical_entity_type,
            canonical_entity_id, canonical_name
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            memory.memory_id,
            memory.scope.tenant_id,
            metadata["canonical_entity_type"],
            metadata["canonical_entity_id"],
            metadata["canonical_name"],
        ),
    )


async def find_existing(
    cursor: MemoryCursor,
    memory: MemoryRecord,
) -> MemoryRecord | None:
    """Return the active record occupying a scoped memory key."""
    await cursor.execute(
        f"""
        SELECT {MEMORY_COLUMNS}
        FROM memory.memories AS m
        LEFT JOIN memory.aliases AS a USING (memory_id)
        WHERE m.agent_id = %s
          AND m.tenant_id = %s
          AND m.scope_type = %s
          AND m.scope_id = %s
          AND m.kind = %s
          AND m.normalized_key = %s
          AND m.status IN ('proposed', 'confirmed')
        """,
        (
            memory.agent_id,
            memory.scope.tenant_id,
            memory.scope.scope_type.value,
            memory.scope.scope_id,
            memory.kind.value,
            memory.normalized_key,
        ),
    )
    row = await cursor.fetchone()
    return memory_from_row(row) if row is not None else None


async def find_by_id(
    cursor: MemoryCursor,
    memory_id: UUID,
    agent_id: str,
    scope: MemoryScope,
    *,
    lock: bool,
) -> MemoryRecord | None:
    """Return one scoped memory, optionally locking it for feedback."""
    suffix = " FOR UPDATE OF m" if lock else ""
    await cursor.execute(
        f"""
        SELECT {MEMORY_COLUMNS}
        FROM memory.memories AS m
        LEFT JOIN memory.aliases AS a USING (memory_id)
        WHERE m.memory_id = %s
          AND m.agent_id = %s
          AND m.tenant_id = %s
          AND m.scope_type = %s
          AND m.scope_id = %s
        {suffix}
        """,
        (
            memory_id,
            agent_id,
            scope.tenant_id,
            scope.scope_type.value,
            scope.scope_id,
        ),
    )
    row = await cursor.fetchone()
    return memory_from_row(row) if row is not None else None


async def find_evidence_outcome(
    cursor: MemoryCursor,
    memory_id: UUID,
    correlation_id: str,
) -> EvidenceOutcome | None:
    """Return the outcome previously recorded for an idempotency key."""
    await cursor.execute(
        """
        SELECT outcome
        FROM memory.evidence
        WHERE memory_id = %s
          AND correlation_id = %s
        """,
        (memory_id, correlation_id),
    )
    row = await cursor.fetchone()
    return EvidenceOutcome(str(row["outcome"])) if row is not None else None


async def update_from_evidence(
    cursor: MemoryCursor,
    memory_id: UUID,
    outcome: EvidenceOutcome,
    promote_after: int,
) -> None:
    """Apply deterministic confirmation or rejection policy."""
    if outcome is EvidenceOutcome.REJECTED:
        await cursor.execute(
            """
            UPDATE memory.memories
            SET status = 'rejected', updated_at = now()
            WHERE memory_id = %s
            """,
            (memory_id,),
        )
        return
    await cursor.execute(
        """
        UPDATE memory.memories
        SET evidence_count = evidence_count + 1,
            confidence = LEAST(
                1.0,
                (evidence_count + 1)::double precision / %s
            ),
            status = CASE
                WHEN evidence_count + 1 >= %s THEN 'confirmed'
                ELSE 'proposed'
            END,
            updated_at = now()
        WHERE memory_id = %s
        """,
        (promote_after, promote_after, memory_id),
    )


def memory_from_row(row: Mapping[str, Any]) -> MemoryRecord:
    """Convert one trusted database row into an immutable memory."""
    metadata = _metadata(row)
    return MemoryRecord(
        memory_id=UUID(str(row["memory_id"])),
        agent_id=str(row["agent_id"]),
        scope=MemoryScope(
            tenant_id=str(row["tenant_id"]),
            scope_type=MemoryScopeType(str(row["scope_type"])),
            scope_id=str(row["scope_id"]),
        ),
        kind=MemoryKind(str(row["kind"])),
        key=str(row["memory_key"]),
        content=str(row["content"]),
        status=MemoryStatus(str(row["status"])),
        confidence=float(row["confidence"]),
        evidence_count=int(row["evidence_count"]),
        metadata=tuple(sorted(metadata.items())),
        embedding=_embedding(row.get("embedding")),
        embedding_model=(
            str(row["embedding_model"]) if row["embedding_model"] is not None else None
        ),
    )


def _metadata(row: Mapping[str, Any]) -> dict[str, str]:
    raw = row["metadata"]
    if isinstance(raw, str):
        raw = json.loads(raw)
    metadata = (
        {str(key): str(value) for key, value in raw.items()}
        if isinstance(raw, Mapping)
        else {}
    )
    for name in (
        "canonical_entity_type",
        "canonical_entity_id",
        "canonical_name",
    ):
        value = row.get(name)
        if value is not None:
            metadata[name] = str(value)
    return metadata


def _embedding(value: object) -> tuple[float, ...]:
    if value is None:
        return ()
    text = str(value).strip()
    if not text.startswith("[") or not text.endswith("]"):
        message = "stored memory embedding is not a PostgreSQL vector"
        raise PostgresMemoryError(message)
    values = text[1:-1]
    return tuple(float(item) for item in values.split(",")) if values else ()
