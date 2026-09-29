"""Deployment environments that warehouse and Cortex adapters resolve against."""

from __future__ import annotations

from enum import StrEnum


class UnknownEnvironmentError(ValueError):
    """Raised when a configured environment name is not recognized."""

    @classmethod
    def for_name(cls, name: str) -> UnknownEnvironmentError:
        """Return an error naming the supported environments."""
        supported = ", ".join(item.value for item in Environment)
        return cls(f"unknown environment {name!r}; supported: {supported}")


class Environment(StrEnum):
    """Where a data call is served from.

    ``SANDBOX`` is served locally by DuckDB over CSV fixtures whose schemas
    mirror the real warehouse. It is the only environment that is
    deterministic by construction, so it is the one benchmarks run against.
    """

    DEV = "dev"
    STAGE = "stage"
    PROD = "prod"
    SANDBOX = "sandbox"

    @classmethod
    def parse(cls, name: str) -> Environment:
        """Return the environment for a configured name, or fail fast."""
        normalized = name.strip().casefold()
        for item in cls:
            if item.value == normalized:
                return item
        raise UnknownEnvironmentError.for_name(name)

    @property
    def is_deterministic(self) -> bool:
        """Return whether repeated calls must return identical results."""
        return self is Environment.SANDBOX

    @property
    def is_production(self) -> bool:
        """Return whether this environment serves real production data."""
        return self is Environment.PROD
