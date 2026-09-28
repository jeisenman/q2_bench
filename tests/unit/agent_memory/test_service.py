import asyncio

import pytest

from adapters.local import InMemoryAgentMemoryStore, MemoryConflictError
from agent_memory import (
    AgentMemory,
    AliasResolutionStatus,
    EvidenceOutcome,
    MemoryKind,
    MemoryScope,
    MemoryScopeType,
    MemoryStatus,
)

CONFIRMATION_THRESHOLD = 3


def memory(
    store: InMemoryAgentMemoryStore,
    *,
    scope_id: str = "data-engineering",
) -> AgentMemory:
    return AgentMemory(
        store,
        agent_id="resource-discovery",
        scope=MemoryScope(
            tenant_id="q2",
            scope_type=MemoryScopeType.TEAM,
            scope_id=scope_id,
        ),
    )


def test_alias_requires_repeated_confirmation_before_resolution() -> None:
    scoped = memory(InMemoryAgentMemoryStore())

    proposed = asyncio.run(
        scoped.propose_alias(
            alias="CNB",
            canonical_entity_type="resource-discovery-client",
            canonical_entity_id="11111111-1111-1111-1111-111111111111",
            canonical_name="City National Bank",
        )
    )

    assert (
        asyncio.run(scoped.resolve_alias("cnb")).status
        is AliasResolutionStatus.CONFIRMATION_REQUIRED
    )
    for index in range(CONFIRMATION_THRESHOLD):
        updated = asyncio.run(
            scoped.record_alias_evidence(
                proposed.memory_id,
                EvidenceOutcome.CONFIRMED,
                correlation_id=f"confirmation-{index}",
            )
        )
    assert updated.evidence_count == CONFIRMATION_THRESHOLD
    assert (
        asyncio.run(scoped.resolve_alias("CNB")).status
        is AliasResolutionStatus.RESOLVED
    )


def test_alias_memory_is_isolated_by_scope() -> None:
    store = InMemoryAgentMemoryStore()
    first = memory(store, scope_id="one")
    second = memory(store, scope_id="two")

    asyncio.run(
        first.propose_alias(
            alias="CNB",
            canonical_entity_type="resource-discovery-client",
            canonical_entity_id="11111111-1111-1111-1111-111111111111",
            canonical_name="City National Bank",
        )
    )

    assert (
        asyncio.run(second.resolve_alias("CNB")).status
        is AliasResolutionStatus.NOT_FOUND
    )


def test_confirmation_is_idempotent_by_correlation_id() -> None:
    scoped = memory(InMemoryAgentMemoryStore())
    proposed = asyncio.run(
        scoped.propose_alias(
            alias="CNB",
            canonical_entity_type="resource-discovery-client",
            canonical_entity_id="11111111-1111-1111-1111-111111111111",
            canonical_name="City National Bank",
        )
    )

    first = asyncio.run(
        scoped.record_alias_evidence(
            proposed.memory_id,
            EvidenceOutcome.CONFIRMED,
            correlation_id="same-request",
        )
    )
    replay = asyncio.run(
        scoped.record_alias_evidence(
            proposed.memory_id,
            EvidenceOutcome.CONFIRMED,
            correlation_id="same-request",
        )
    )

    assert first.evidence_count == 1
    assert replay.evidence_count == 1


def test_conflicting_alias_meaning_fails_fast() -> None:
    scoped = memory(InMemoryAgentMemoryStore())
    values = {
        "alias": "CNB",
        "canonical_entity_type": "resource-discovery-client",
        "canonical_entity_id": "11111111-1111-1111-1111-111111111111",
        "canonical_name": "City National Bank",
    }
    asyncio.run(scoped.propose_alias(**values))
    values["canonical_name"] = "Conflicting Name"

    with pytest.raises(MemoryConflictError, match="different meaning"):
        asyncio.run(scoped.propose_alias(**values))


def test_memory_service_rejects_invalid_configuration() -> None:
    store = InMemoryAgentMemoryStore()
    configured_scope = MemoryScope(
        tenant_id="q2",
        scope_type=MemoryScopeType.TEAM,
        scope_id="data-engineering",
    )

    with pytest.raises(ValueError, match="agent_id"):
        AgentMemory(store, agent_id=" ", scope=configured_scope)
    with pytest.raises(ValueError, match="at least 1"):
        AgentMemory(
            store,
            agent_id="resource-discovery",
            scope=configured_scope,
            alias_confirmations=0,
        )


def test_memory_service_stores_confirmed_summary() -> None:
    scoped = memory(InMemoryAgentMemoryStore())

    remembered = asyncio.run(
        scoped.remember_summary(
            key="US-01:dag:task:run",
            content="US-01 dag task: confirmed_oom",
            metadata=(("diagnosis", "confirmed_oom"),),
        )
    )

    assert remembered.kind is MemoryKind.SUMMARY
    assert remembered.status is MemoryStatus.CONFIRMED
    assert remembered.confidence == 1.0
    assert remembered.evidence_count == 1


def test_rejection_removes_alias_and_conflicting_replay_fails() -> None:
    scoped = memory(InMemoryAgentMemoryStore())
    proposed = asyncio.run(
        scoped.propose_alias(
            alias="CNB",
            canonical_entity_type="resource-discovery-client",
            canonical_entity_id="11111111-1111-1111-1111-111111111111",
            canonical_name="City National Bank",
        )
    )
    rejected = asyncio.run(
        scoped.record_alias_evidence(
            proposed.memory_id,
            EvidenceOutcome.REJECTED,
            correlation_id="feedback-1",
        )
    )

    assert rejected.status.value == "rejected"
    assert (
        asyncio.run(scoped.resolve_alias("CNB")).status
        is AliasResolutionStatus.NOT_FOUND
    )
    with pytest.raises(MemoryConflictError, match="different evidence"):
        asyncio.run(
            scoped.record_alias_evidence(
                proposed.memory_id,
                EvidenceOutcome.CONFIRMED,
                correlation_id="feedback-1",
            )
        )
