"""Typed contract for Snowflake Cortex inference.

Cortex is model inference, so it is not deterministic and cannot be emulated
by the DuckDB sandbox. It is a separate port for exactly that reason: the
sandbox double replays recorded responses instead of reproducing data, and
keeping the two apart stops an LLM call from ending up inside a query a
benchmark asserts on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from domain.environments import Environment


@dataclass(frozen=True, slots=True)
class CortexRequest:
    """One Cortex completion request."""

    model: str
    prompt: str
    temperature: float = 0.0

    def __post_init__(self) -> None:
        """Validate the request at the boundary."""
        if not self.model.strip():
            message = "model must not be empty"
            raise ValueError(message)
        if not self.prompt.strip():
            message = "prompt must not be empty"
            raise ValueError(message)
        if not 0.0 <= self.temperature <= 1.0:
            message = f"temperature must be between 0.0 and 1.0; got {self.temperature}"
            raise ValueError(message)


@dataclass(frozen=True, slots=True)
class CortexResponse:
    """One Cortex completion, with the environment that produced it."""

    text: str
    model: str
    environment: Environment
    recorded: bool = False
    """True when replayed from a fixture rather than produced by live inference."""


class CortexError(RuntimeError):
    """Raised when a Cortex request cannot be completed."""


class CortexUnavailableError(CortexError):
    """Raised when Cortex is not reachable in the resolved environment."""


class CortexInference(Protocol):
    """Run a Cortex completion against one resolved environment."""

    @property
    def environment(self) -> Environment:
        """Return the environment this adapter is bound to."""
        ...

    async def complete(self, request: CortexRequest) -> CortexResponse:
        """Return one completion, or raise when Cortex is unavailable."""
        ...

    async def count_tokens(self, model: str, text: str) -> int:
        """Return the token count for text, without running inference."""
        ...
