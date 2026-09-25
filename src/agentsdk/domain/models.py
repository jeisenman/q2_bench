"""Immutable models shared by agents, runtimes, and benchmark tooling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias

Scalar: TypeAlias = str | int | float | bool | None
Attributes: TypeAlias = tuple[tuple[str, Scalar], ...]


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        message = f"{field_name} must not be empty"
        raise ValueError(message)


@dataclass(frozen=True, slots=True)
class BenchmarkIdentity:
    """Identify a benchmark within a hierarchical benchmark group."""

    group: str
    name: str
    version: str = "1"
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate identity fields."""
        _require_text(self.group, "group")
        _require_text(self.name, "name")
        _require_text(self.version, "version")

    @property
    def qualified_name(self) -> str:
        """Return a stable group/name identifier."""
        return f"{self.group}/{self.name}"


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Describe an agent capability independently of a tool framework."""

    name: str
    description: str
    input_schema: Attributes = ()

    def __post_init__(self) -> None:
        """Validate required tool metadata."""
        _require_text(self.name, "name")
        _require_text(self.description, "description")


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    """Describe an agent and the tools a runtime may expose."""

    name: str
    description: str
    instructions: str
    tools: tuple[ToolDefinition, ...] = ()
    version: str = "1"

    def __post_init__(self) -> None:
        """Validate required agent metadata and unique tool names."""
        _require_text(self.name, "name")
        _require_text(self.description, "description")
        _require_text(self.instructions, "instructions")
        _require_text(self.version, "version")
        names = tuple(tool.name for tool in self.tools)
        if len(names) != len(set(names)):
            msg = f"agent {self.name!r} contains duplicate tool names"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class AgentRequest:
    """Represent one framework-neutral request to an agent."""

    prompt: str
    correlation_id: str
    attributes: Attributes = ()

    def __post_init__(self) -> None:
        """Validate required request values."""
        _require_text(self.prompt, "prompt")
        _require_text(self.correlation_id, "correlation_id")


@dataclass(frozen=True, slots=True)
class AgentResult:
    """Represent the deterministic output metadata returned by a runtime."""

    output: str
    correlation_id: str
    tool_calls: tuple[str, ...] = ()
    attributes: Attributes = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Validate result correlation."""
        _require_text(self.correlation_id, "correlation_id")
