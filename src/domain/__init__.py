"""Framework-neutral domain contracts."""

from domain.environments import Environment, UnknownEnvironmentError
from domain.models import (
    AgentDefinition,
    AgentRequest,
    AgentResult,
    BenchmarkIdentity,
    Scalar,
    ToolDefinition,
)
from domain.sql_portability import (
    PortabilityRule,
    SqlPortabilityError,
    is_cortex_call,
    portability_violations,
    require_portable,
)

__all__ = [
    "AgentDefinition",
    "AgentRequest",
    "AgentResult",
    "BenchmarkIdentity",
    "Environment",
    "PortabilityRule",
    "Scalar",
    "SqlPortabilityError",
    "ToolDefinition",
    "UnknownEnvironmentError",
    "is_cortex_call",
    "portability_violations",
    "require_portable",
]
