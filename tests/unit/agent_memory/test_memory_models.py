from dataclasses import replace
from math import nan
from typing import Any
from uuid import UUID

import pytest

from agent_memory import (
    AliasResolution,
    AliasResolutionStatus,
    EvidenceOutcome,
    MemoryEvidence,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryScopeType,
    MemoryStatus,
    normalize_memory_key,
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
    )


def test_normalized_keys_are_stable_and_nonempty() -> None:
    assert normalize_memory_key(" C.N.B. ") == "c n b"
    with pytest.raises(ValueError, match="memory key"):
        normalize_memory_key(" ")


@pytest.mark.parametrize("field", ["tenant_id", "scope_id"])
def test_scope_requires_all_isolation_fields(field: str) -> None:
    values = {
        "tenant_id": "q2",
        "scope_type": MemoryScopeType.TEAM,
        "scope_id": "data-engineering",
    }
    values[field] = " "
    with pytest.raises(ValueError, match=field):
        MemoryScope(**values)


def test_scope_requires_typed_visibility() -> None:
    with pytest.raises(TypeError, match="MemoryScopeType"):
        MemoryScope("q2", "team", "data-engineering")  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["agent_id", "key", "content"])
def test_memory_requires_bounded_text(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        replace(record(), **{field: " "})


def test_memory_requires_typed_kind_and_status() -> None:
    with pytest.raises(TypeError, match="MemoryKind"):
        replace(record(), kind="alias")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="MemoryStatus"):
        replace(record(), status="proposed")  # type: ignore[arg-type]


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_memory_rejects_invalid_confidence(confidence: float) -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        replace(record(), confidence=confidence)


def test_memory_rejects_invalid_evidence_metadata_and_vectors() -> None:
    with pytest.raises(ValueError, match="negative"):
        replace(record(), evidence_count=-1)
    with pytest.raises(ValueError, match="unique"):
        replace(record(), metadata=(("name", "one"), ("name", "two")))
    with pytest.raises(ValueError, match="finite"):
        replace(record(), embedding=(nan,), embedding_model="test")
    with pytest.raises(ValueError, match="embedding_model"):
        replace(record(), embedding=(1.0,))


def test_memory_metadata_is_immutable() -> None:
    memory = replace(record(), metadata=(("name", "City National Bank"),))

    assert memory.metadata_mapping["name"] == "City National Bank"
    with pytest.raises(TypeError):
        memory.metadata_mapping["name"] = "changed"  # type: ignore[index]


def test_evidence_requires_typed_outcome_and_correlation() -> None:
    with pytest.raises(TypeError, match="EvidenceOutcome"):
        MemoryEvidence(MEMORY_ID, "confirmed", "request")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="correlation_id"):
        MemoryEvidence(MEMORY_ID, EvidenceOutcome.CONFIRMED, " ")


def test_alias_resolution_returns_only_a_unique_match() -> None:
    memory = replace(record(), status=MemoryStatus.CONFIRMED)

    assert AliasResolution(AliasResolutionStatus.RESOLVED, (memory,)).unique == memory
    assert (
        AliasResolution(AliasResolutionStatus.AMBIGUOUS, (memory, memory)).unique
        is None
    )


def test_runtime_invalid_values_remain_rejected() -> None:
    invalid: Any = object()
    with pytest.raises(TypeError):
        replace(record(), kind=invalid)
