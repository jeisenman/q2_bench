import asyncio
from dataclasses import replace
from typing import Any
from uuid import UUID

import pytest

from adapters.postgres import PostgresMemoryError
from adapters.postgres.memory_sql import (
    find_evidence_outcome,
    insert_alias,
    insert_values,
    memory_from_row,
    update_from_evidence,
)
from agent_memory import (
    EvidenceOutcome,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryScopeType,
)

MEMORY_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def scope() -> MemoryScope:
    return MemoryScope("q2", MemoryScopeType.TEAM, "data-engineering")


def record() -> MemoryRecord:
    return MemoryRecord(
        memory_id=MEMORY_ID,
        agent_id="resource-discovery",
        scope=scope(),
        kind=MemoryKind.ALIAS,
        key="CNB",
        content="CNB refers to City National Bank",
        metadata=(
            ("canonical_entity_id", "11111111-1111-1111-1111-111111111111"),
            ("canonical_entity_type", "resource-discovery-client"),
            ("canonical_name", "City National Bank"),
        ),
    )


def row() -> dict[str, Any]:
    return {
        "memory_id": MEMORY_ID,
        "agent_id": "resource-discovery",
        "tenant_id": "q2",
        "scope_type": "team",
        "scope_id": "data-engineering",
        "kind": "alias",
        "memory_key": "CNB",
        "content": "CNB refers to City National Bank",
        "status": "proposed",
        "confidence": 0.0,
        "evidence_count": 0,
        "metadata": {},
        "embedding": None,
        "embedding_model": None,
        "canonical_entity_type": "resource-discovery-client",
        "canonical_entity_id": "11111111-1111-1111-1111-111111111111",
        "canonical_name": "City National Bank",
    }


class FakeCursor:
    def __init__(self, *, evidence_outcome: str | None = "confirmed") -> None:
        self.evidence_outcome = evidence_outcome
        self.statements: list[str] = []
        self._one: dict[str, Any] | None = None

    async def execute(self, query: object, _parameters: object = None) -> None:
        statement = str(query)
        self.statements.append(statement)
        self._one = None
        if "SELECT outcome" in statement and self.evidence_outcome is not None:
            self._one = {"outcome": self.evidence_outcome}

    async def fetchone(self) -> dict[str, Any] | None:
        return self._one


def test_sql_helpers_preserve_vectors_and_validate_aliases() -> None:
    embedded = replace(
        record(),
        embedding=(1.0, 2.0),
        embedding_model="test-embedding",
    )
    values = insert_values(embedded)
    assert values[-2] == "[1.0,2.0]"
    embedded_row = row()
    embedded_row["embedding"] = "[1,2]"
    embedded_row["embedding_model"] = "test-embedding"
    assert memory_from_row(embedded_row).embedding == (1.0, 2.0)
    embedded_row["embedding"] = "[]"
    assert memory_from_row(embedded_row).embedding == ()
    embedded_row["embedding"] = "invalid"
    with pytest.raises(PostgresMemoryError, match="not a PostgreSQL vector"):
        memory_from_row(embedded_row)


def test_sql_helpers_cover_rejection_and_missing_alias_metadata() -> None:
    cursor: Any = FakeCursor()
    asyncio.run(
        update_from_evidence(
            cursor,
            MEMORY_ID,
            EvidenceOutcome.REJECTED,
            3,
        )
    )
    assert any("status = 'rejected'" in item for item in cursor.statements)
    invalid = MemoryRecord(
        memory_id=MEMORY_ID,
        agent_id="resource-discovery",
        scope=scope(),
        kind=MemoryKind.ALIAS,
        key="CNB",
        content="Incomplete alias",
    )
    with pytest.raises(PostgresMemoryError, match="canonical entity metadata"):
        asyncio.run(insert_alias(cursor, invalid))

    non_alias = replace(invalid, kind=MemoryKind.FACT)
    asyncio.run(insert_alias(cursor, non_alias))


def test_find_evidence_outcome_returns_typed_value_or_none() -> None:
    confirmed_cursor: Any = FakeCursor(evidence_outcome="confirmed")
    confirmed = asyncio.run(
        find_evidence_outcome(confirmed_cursor, MEMORY_ID, "confirmation-1")
    )
    assert confirmed is EvidenceOutcome.CONFIRMED

    missing_cursor: Any = FakeCursor(evidence_outcome=None)
    missing = asyncio.run(
        find_evidence_outcome(missing_cursor, MEMORY_ID, "confirmation-1")
    )
    assert missing is None
