"""Framework-neutral domain contracts."""

from domain.models import (
    AgentDefinition,
    AgentRequest,
    AgentResult,
    BenchmarkIdentity,
    Scalar,
    ToolDefinition,
)

__all__ = [
    "AgentDefinition",
    "AgentRequest",
    "AgentResult",
    "BenchmarkIdentity",
    "Scalar",
    "ToolDefinition",
]
