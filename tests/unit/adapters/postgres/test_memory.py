import asyncio
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from psycopg import OperationalError

from adapters.postgres import (
    AGENT_MEMORY_CONFIRMATIONS_ENV,
    AGENT_MEMORY_DSN_ENV,
    AGENT_MEMORY_SCOPE_ID_ENV,
    AGENT_MEMORY_SCOPE_TYPE_ENV,
    AGENT_MEMORY_TENANT_ENV,
    AgentMemoryCompositionError,
    PostgresAgentMemoryStore,
    PostgresMemoryConfigurationError,
    PostgresMemoryError,
    agent_memory_from_environment,
)
from adapters.postgres import memory as memory_module
from agent_memory import (
    AgentMemory,
    EvidenceOutcome,
    MemoryEvidence,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryScopeType,
)

ROOT = Path(__file__).parents[4]
MIGRATION = ROOT / "migrations/postgres/001_agent_memory.sql"
MEMORY_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
EXPECTED_CONFIRMATIONS = 2
PROVIDER_ERROR = OperationalError("database unavailable")


def scope() -> MemoryScope:
    return MemoryScope("q2", MemoryScopeType.TEAM, "data-engineering")


def record(*, evidence_count: int = 0) -> MemoryRecord:
    return MemoryRecord(
        memory_id=MEMORY_ID,
        agent_id="resource-discovery",
        scope=scope(),
        kind=MemoryKind.ALIAS,
        key="CNB",
        content="CNB refers to City National Bank",
        evidence_count=evidence_count,
        metadata=(
            ("canonical_entity_id", "11111111-1111-1111-1111-111111111111"),
            ("canonical_entity_type", "resource-discovery-client"),
            ("canonical_name", "City National Bank"),
        ),
    )


def row(*, evidence_count: int = 0, status: str = "proposed") -> dict[str, Any]:
    return {
        "memory_id": MEMORY_ID,
        "agent_id": "resource-discovery",
        "tenant_id": "q2",
        "scope_type": "team",
        "scope_id": "data-engineering",
        "kind": "alias",
        "memory_key": "CNB",
        "content": "CNB refers to City National Bank",
        "status": status,
        "confidence": evidence_count / 3,
        "evidence_count": evidence_count,
        "metadata": {},
        "embedding": None,
        "embedding_model": None,
        "canonical_entity_type": "resource-discovery-client",
        "canonical_entity_id": "11111111-1111-1111-1111-111111111111",
        "canonical_name": "City National Bank",
    }


class FakeCursor:
    def __init__(
        self,
        *,
        exact_rows: list[dict[str, Any]] | None = None,
        id_rows: list[dict[str, Any]] | None = None,
        memory_inserted: bool = True,
        evidence_inserted: bool = True,
        evidence_outcome: str | None = "confirmed",
    ) -> None:
        self.exact_rows = exact_rows or []
        self.id_rows = id_rows or []
        self.memory_inserted = memory_inserted
        self.evidence_inserted = evidence_inserted
        self.evidence_outcome = evidence_outcome
        self.statements: list[str] = []
        self._one: dict[str, Any] | None = None
        self._all: list[dict[str, Any]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, query, _parameters=None) -> None:
        statement = str(query)
        self.statements.append(statement)
        self._one = None
        self._all = []
        if "RETURNING memory_id" in statement:
            self._one = {"memory_id": MEMORY_ID} if self.memory_inserted else None
        elif "RETURNING evidence_id" in statement:
            self._one = {"evidence_id": MEMORY_ID} if self.evidence_inserted else None
        elif "SELECT outcome" in statement:
            self._one = (
                {"outcome": self.evidence_outcome}
                if self.evidence_outcome is not None
                else None
            )
        elif "WHERE m.memory_id" in statement:
            self._one = self.id_rows.pop(0) if self.id_rows else None
        elif "m.normalized_key" in statement:
            self._all = self.exact_rows
            self._one = self.exact_rows[0] if self.exact_rows else None

    async def fetchone(self):
        return self._one

    async def fetchall(self):
        return self._all


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def cursor(self, **_kwargs):
        return self._cursor


def install_connection(
    monkeypatch: pytest.MonkeyPatch,
    cursor: FakeCursor,
) -> None:
    async def connect(_dsn: str) -> FakeConnection:
        return FakeConnection(cursor)

    monkeypatch.setattr(memory_module.psycopg.AsyncConnection, "connect", connect)


def test_memory_migration_defines_vectorized_tenant_scoped_schema() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE SCHEMA IF NOT EXISTS memory" in sql
    assert "embedding vector" in sql
    assert "CREATE TABLE IF NOT EXISTS memory.aliases" in sql
    assert "CREATE TABLE IF NOT EXISTS memory.evidence" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "current_setting('app.tenant_id', true)" in sql
    assert "FOREIGN KEY (memory_id, tenant_id)" in sql
    assert "UNIQUE (memory_id, correlation_id)" in sql


def test_memory_composition_is_optional_without_dsn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(AGENT_MEMORY_DSN_ENV, raising=False)

    assert agent_memory_from_environment("resource-discovery") is None


def test_partial_memory_configuration_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(AGENT_MEMORY_DSN_ENV, "postgresql://memory")
    monkeypatch.delenv(AGENT_MEMORY_TENANT_ENV, raising=False)
    monkeypatch.setenv(AGENT_MEMORY_SCOPE_ID_ENV, "data-engineering")

    with pytest.raises(AgentMemoryCompositionError, match=AGENT_MEMORY_TENANT_ENV):
        agent_memory_from_environment("resource-discovery")


def test_complete_environment_builds_scoped_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(AGENT_MEMORY_DSN_ENV, "postgresql://memory")
    monkeypatch.setenv(AGENT_MEMORY_TENANT_ENV, "q2")
    monkeypatch.setenv(AGENT_MEMORY_SCOPE_ID_ENV, "data-engineering")
    monkeypatch.setenv(AGENT_MEMORY_SCOPE_TYPE_ENV, "team")
    monkeypatch.setenv(
        AGENT_MEMORY_CONFIRMATIONS_ENV,
        str(EXPECTED_CONFIRMATIONS),
    )

    configured = agent_memory_from_environment("resource-discovery")

    assert isinstance(configured, AgentMemory)
    assert configured.scope == scope()
    assert configured.alias_confirmations == EXPECTED_CONFIRMATIONS


def test_invalid_environment_values_fail_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(AGENT_MEMORY_DSN_ENV, "postgresql://memory")
    monkeypatch.setenv(AGENT_MEMORY_TENANT_ENV, "q2")
    monkeypatch.setenv(AGENT_MEMORY_SCOPE_ID_ENV, "data-engineering")
    monkeypatch.setenv(AGENT_MEMORY_SCOPE_TYPE_ENV, "unknown")

    with pytest.raises(AgentMemoryCompositionError, match="must be one of"):
        agent_memory_from_environment("resource-discovery")

    monkeypatch.setenv(AGENT_MEMORY_SCOPE_TYPE_ENV, "team")
    monkeypatch.setenv(AGENT_MEMORY_CONFIRMATIONS_ENV, "not-an-integer")
    with pytest.raises(AgentMemoryCompositionError, match="must be an integer"):
        agent_memory_from_environment("resource-discovery")


def test_postgres_configuration_validates_dsn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        PostgresAgentMemoryStore(" ")
    monkeypatch.delenv(AGENT_MEMORY_DSN_ENV, raising=False)
    with pytest.raises(PostgresMemoryConfigurationError, match=AGENT_MEMORY_DSN_ENV):
        PostgresAgentMemoryStore.from_environment()


def test_postgres_store_reads_and_inserts_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    find_cursor = FakeCursor(exact_rows=[row()])
    install_connection(monkeypatch, find_cursor)
    store = PostgresAgentMemoryStore("postgresql://memory")

    found = asyncio.run(
        store.find(
            agent_id="resource-discovery",
            scope=scope(),
            kind=MemoryKind.ALIAS,
            normalized_key="cnb",
        )
    )

    assert found == (record(),)
    insert_cursor = FakeCursor()
    install_connection(monkeypatch, insert_cursor)
    assert asyncio.run(store.put(record())) == record()
    assert any(
        "INSERT INTO memory.aliases" in item for item in insert_cursor.statements
    )


def test_postgres_store_returns_existing_and_rejects_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_cursor = FakeCursor(
        exact_rows=[row()],
        memory_inserted=False,
    )
    install_connection(monkeypatch, existing_cursor)
    store = PostgresAgentMemoryStore("postgresql://memory")

    assert asyncio.run(store.put(record())) == record()

    conflict_row = row()
    conflict_row["canonical_name"] = "Different Bank"
    conflict_cursor = FakeCursor(
        exact_rows=[conflict_row],
        memory_inserted=False,
    )
    install_connection(monkeypatch, conflict_cursor)
    with pytest.raises(PostgresMemoryError, match="different meaning"):
        asyncio.run(store.put(record()))


def test_postgres_store_records_and_replays_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updated = row(evidence_count=1)
    cursor = FakeCursor(id_rows=[row(), updated])
    install_connection(monkeypatch, cursor)
    store = PostgresAgentMemoryStore("postgresql://memory")
    evidence = MemoryEvidence(
        MEMORY_ID,
        EvidenceOutcome.CONFIRMED,
        "confirmation-1",
    )

    result = asyncio.run(
        store.record_evidence(
            agent_id="resource-discovery",
            scope=scope(),
            evidence=evidence,
            promote_after=3,
        )
    )

    assert result.evidence_count == 1
    replay_cursor = FakeCursor(
        id_rows=[updated],
        evidence_inserted=False,
    )
    install_connection(monkeypatch, replay_cursor)
    replay = asyncio.run(
        store.record_evidence(
            agent_id="resource-discovery",
            scope=scope(),
            evidence=evidence,
            promote_after=3,
        )
    )
    assert replay.evidence_count == 1

    conflict_cursor = FakeCursor(
        id_rows=[updated],
        evidence_inserted=False,
        evidence_outcome="rejected",
    )
    install_connection(monkeypatch, conflict_cursor)
    with pytest.raises(PostgresMemoryError, match="different outcome"):
        asyncio.run(
            store.record_evidence(
                agent_id="resource-discovery",
                scope=scope(),
                evidence=evidence,
                promote_after=3,
            )
        )

    unresolved_cursor = FakeCursor(
        id_rows=[updated],
        evidence_inserted=False,
        evidence_outcome=None,
    )
    install_connection(monkeypatch, unresolved_cursor)
    with pytest.raises(PostgresMemoryError, match="could not be resolved"):
        asyncio.run(
            store.record_evidence(
                agent_id="resource-discovery",
                scope=scope(),
                evidence=evidence,
                promote_after=3,
            )
        )


def test_postgres_store_wraps_provider_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail(_dsn: str):
        raise PROVIDER_ERROR

    monkeypatch.setattr(memory_module.psycopg.AsyncConnection, "connect", fail)
    store = PostgresAgentMemoryStore("postgresql://memory")

    with pytest.raises(PostgresMemoryError, match="unable to query"):
        asyncio.run(
            store.find(
                agent_id="resource-discovery",
                scope=scope(),
                kind=MemoryKind.ALIAS,
                normalized_key="cnb",
            )
        )
