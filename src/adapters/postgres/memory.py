"""Persist scoped agent memories in PostgreSQL with tenant isolation."""

from __future__ import annotations

import os

import psycopg
from psycopg.rows import dict_row

from adapters.postgres.errors import (
    PostgresMemoryConfigurationError,
    PostgresMemoryError,
)
from adapters.postgres.memory_sql import (
    MEMORY_COLUMNS,
    find_by_id,
    find_evidence_outcome,
    find_existing,
    insert_alias,
    insert_values,
    memory_from_row,
    set_tenant,
    update_from_evidence,
)
from agent_memory import MemoryEvidence, MemoryKind, MemoryRecord, MemoryScope

AGENT_MEMORY_DSN_ENV = "AGENT_MEMORY_POSTGRES_DSN"


class PostgresAgentMemoryStore:
    """Store agent memories using short PostgreSQL transactions."""

    def __init__(self, dsn: str) -> None:
        """Initialize with an explicit PostgreSQL connection string."""
        if not dsn.strip():
            message = "agent memory PostgreSQL DSN must not be empty"
            raise ValueError(message)
        self._dsn = dsn

    @classmethod
    def from_environment(cls) -> PostgresAgentMemoryStore:
        """Build the adapter from the required memory DSN environment value."""
        dsn = os.environ.get(AGENT_MEMORY_DSN_ENV)
        if not dsn:
            message = f"{AGENT_MEMORY_DSN_ENV} is required for durable agent memory"
            raise PostgresMemoryConfigurationError(message)
        return cls(dsn)

    async def find(
        self,
        *,
        agent_id: str,
        scope: MemoryScope,
        kind: MemoryKind,
        normalized_key: str,
    ) -> tuple[MemoryRecord, ...]:
        """Return active exact-key memories visible to one tenant and scope."""
        query = f"""
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
            ORDER BY m.status = 'confirmed' DESC, m.confidence DESC, m.memory_id
        """
        try:
            connection = await psycopg.AsyncConnection.connect(self._dsn)
            async with connection, connection.cursor(row_factory=dict_row) as cursor:
                await set_tenant(cursor, scope)
                await cursor.execute(
                    query,
                    (
                        agent_id,
                        scope.tenant_id,
                        scope.scope_type.value,
                        scope.scope_id,
                        kind.value,
                        normalized_key,
                    ),
                )
                rows = await cursor.fetchall()
        except psycopg.Error as error:
            message = f"unable to query agent memory: {error}"
            raise PostgresMemoryError(message) from error
        return tuple(memory_from_row(row) for row in rows)

    async def put(self, memory: MemoryRecord) -> MemoryRecord:
        """Insert one memory or return an identical active scoped memory."""
        insert = """
            INSERT INTO memory.memories (
                memory_id, agent_id, tenant_id, scope_type, scope_id, kind,
                memory_key, normalized_key, content, status, confidence,
                evidence_count, metadata, embedding, embedding_model
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s::vector, %s
            )
            ON CONFLICT (
                agent_id, tenant_id, scope_type, scope_id, kind, normalized_key
            ) WHERE status IN ('proposed', 'confirmed')
            DO NOTHING
            RETURNING memory_id
        """
        try:
            connection = await psycopg.AsyncConnection.connect(self._dsn)
            async with connection, connection.cursor(row_factory=dict_row) as cursor:
                await set_tenant(cursor, memory.scope)
                await cursor.execute(insert, insert_values(memory))
                inserted = await cursor.fetchone()
                if inserted is not None:
                    await insert_alias(cursor, memory)
                    return memory
                existing = await find_existing(cursor, memory)
                if existing is None:
                    message = "memory conflict could not be resolved"
                    raise PostgresMemoryError(message)
                if existing.metadata != memory.metadata:
                    message = (
                        f"memory key {memory.key!r} already has a different meaning"
                    )
                    raise PostgresMemoryError(message)
                return existing
        except psycopg.Error as error:
            message = f"unable to persist agent memory: {error}"
            raise PostgresMemoryError(message) from error

    async def record_evidence(
        self,
        *,
        agent_id: str,
        scope: MemoryScope,
        evidence: MemoryEvidence,
        promote_after: int,
    ) -> MemoryRecord:
        """Append evidence and atomically promote or reject a memory."""
        try:
            connection = await psycopg.AsyncConnection.connect(self._dsn)
            async with connection, connection.cursor(row_factory=dict_row) as cursor:
                await set_tenant(cursor, scope)
                existing = await find_by_id(
                    cursor,
                    evidence.memory_id,
                    agent_id,
                    scope,
                    lock=True,
                )
                if existing is None:
                    message = (
                        f"memory {evidence.memory_id} was not found "
                        "in the requested scope"
                    )
                    raise PostgresMemoryError(message)
                await cursor.execute(
                    """
                    INSERT INTO memory.evidence (
                        evidence_id, memory_id, tenant_id, outcome,
                        correlation_id
                    )
                    VALUES (gen_random_uuid(), %s, %s, %s, %s)
                    ON CONFLICT (memory_id, correlation_id) DO NOTHING
                    RETURNING evidence_id
                    """,
                    (
                        evidence.memory_id,
                        scope.tenant_id,
                        evidence.outcome.value,
                        evidence.correlation_id,
                    ),
                )
                inserted = await cursor.fetchone()
                if inserted is None:
                    previous_outcome = await find_evidence_outcome(
                        cursor,
                        evidence.memory_id,
                        evidence.correlation_id,
                    )
                    if previous_outcome is None:
                        message = "memory evidence conflict could not be resolved"
                        raise PostgresMemoryError(message)
                    if previous_outcome is not evidence.outcome:
                        message = (
                            f"correlation_id {evidence.correlation_id!r} "
                            "was already used with a different outcome"
                        )
                        raise PostgresMemoryError(message)
                    return existing
                await update_from_evidence(
                    cursor,
                    evidence.memory_id,
                    evidence.outcome,
                    promote_after,
                )
                updated = await find_by_id(
                    cursor,
                    evidence.memory_id,
                    agent_id,
                    scope,
                    lock=False,
                )
                assert updated is not None
                return updated
        except psycopg.Error as error:
            message = f"unable to record agent memory evidence: {error}"
            raise PostgresMemoryError(message) from error
