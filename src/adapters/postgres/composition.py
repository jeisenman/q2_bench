"""Environment-driven composition for scoped PostgreSQL agent memory."""

from __future__ import annotations

import os

from adapters.postgres.memory import (
    AGENT_MEMORY_DSN_ENV,
    PostgresAgentMemoryStore,
)
from agent_memory import AgentMemory, MemoryScope, MemoryScopeType

AGENT_MEMORY_TENANT_ENV = "AGENT_MEMORY_TENANT_ID"
AGENT_MEMORY_SCOPE_TYPE_ENV = "AGENT_MEMORY_SCOPE_TYPE"
AGENT_MEMORY_SCOPE_ID_ENV = "AGENT_MEMORY_SCOPE_ID"
AGENT_MEMORY_CONFIRMATIONS_ENV = "AGENT_MEMORY_ALIAS_CONFIRMATIONS"


class AgentMemoryCompositionError(ValueError):
    """Raised when partial or invalid memory configuration is supplied."""


def agent_memory_from_environment(agent_id: str) -> AgentMemory | None:
    """Return configured durable memory or disable it when no DSN is supplied."""
    if not os.environ.get(AGENT_MEMORY_DSN_ENV):
        return None
    tenant_id = _required(AGENT_MEMORY_TENANT_ENV)
    scope_id = _required(AGENT_MEMORY_SCOPE_ID_ENV)
    scope_type_value = os.environ.get(
        AGENT_MEMORY_SCOPE_TYPE_ENV,
        MemoryScopeType.ORGANIZATION.value,
    )
    try:
        scope_type = MemoryScopeType(scope_type_value)
    except ValueError as error:
        allowed = ", ".join(item.value for item in MemoryScopeType)
        message = f"{AGENT_MEMORY_SCOPE_TYPE_ENV} must be one of: {allowed}"
        raise AgentMemoryCompositionError(message) from error
    confirmations_value = os.environ.get(AGENT_MEMORY_CONFIRMATIONS_ENV, "3")
    try:
        confirmations = int(confirmations_value)
    except ValueError as error:
        message = f"{AGENT_MEMORY_CONFIRMATIONS_ENV} must be an integer"
        raise AgentMemoryCompositionError(message) from error
    return AgentMemory(
        PostgresAgentMemoryStore.from_environment(),
        agent_id=agent_id,
        scope=MemoryScope(tenant_id, scope_type, scope_id),
        alias_confirmations=confirmations,
    )


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        message = f"{name} is required when {AGENT_MEMORY_DSN_ENV} is configured"
        raise AgentMemoryCompositionError(message)
    return value
