import pytest

from workspaces.data_engineering.agents import AgentRegistry


def test_registry_builds_preconfigured_agent() -> None:
    registry = AgentRegistry()
    sentinel = object()
    registry.register("prod-support", lambda: sentinel)

    assert registry.create("prod-support") is sentinel
    assert registry.names() == ("prod-support",)


def test_registry_rejects_empty_and_duplicate_names() -> None:
    registry = AgentRegistry()

    with pytest.raises(ValueError, match="must not be empty"):
        registry.register(" ", object)

    registry.register("prod-support", object)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("prod-support", object)


def test_registry_reports_unknown_agent() -> None:
    with pytest.raises(LookupError, match="available agents: none"):
        AgentRegistry().create("missing")
