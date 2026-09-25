"""Dependency-injected registry for data-engineering agents."""

from collections.abc import Callable

from workspaces.data_engineering.agents.contracts import WorkspaceAgent

AgentFactory = Callable[[], WorkspaceAgent]


class AgentRegistry:
    """Register named factories and build agents with injected data providers."""

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._factories: dict[str, AgentFactory] = {}

    def register(self, name: str, factory: AgentFactory) -> None:
        """Register a unique agent factory."""
        if not name.strip():
            message = "agent name must not be empty"
            raise ValueError(message)
        if name in self._factories:
            message = f"agent {name!r} is already registered"
            raise ValueError(message)
        self._factories[name] = factory

    def create(self, name: str) -> WorkspaceAgent:
        """Build a named agent from its dependency-injected factory."""
        try:
            factory = self._factories[name]
        except KeyError as error:
            available = ", ".join(sorted(self._factories)) or "none"
            message = f"unknown agent {name!r}; available agents: {available}"
            raise LookupError(message) from error
        return factory()

    def names(self) -> tuple[str, ...]:
        """Return registered names in deterministic order."""
        return tuple(sorted(self._factories))
