"""Typed contracts for benchmarked orchestrator-to-agent handoffs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

MAX_HANDOFF_PARALLELISM = 5


class HandoffContractError(ValueError):
    """Raised when a benchmark handoff contract is invalid."""

    @classmethod
    def invalid(cls, path: Path, reason: str) -> HandoffContractError:
        """Create an error identifying the invalid handoff contract."""
        return cls(f"{path}: {reason}")


@dataclass(frozen=True, slots=True)
class HandoffAgentContract:
    """Expected invocation and payload behavior for one named agent."""

    name: str
    parent: str
    min_calls: int
    max_calls: int
    starts_after: tuple[str, ...] = ()
    required_input_fields: tuple[str, ...] = ()
    required_output_fields: tuple[str, ...] = ()
    expected_mode: str = "execute"
    can_delegate: bool = False


@dataclass(frozen=True, slots=True)
class HandoffContract:
    """Expected named-agent graph for one benchmark case."""

    max_parallel: int
    agents: tuple[HandoffAgentContract, ...]
    output_authority: str | None = None


def parse_handoff_contract(raw: object, path: Path) -> HandoffContract | None:
    """Parse and validate an optional handoff contract."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise HandoffContractError.invalid(
            path,
            "handoff_contract must be a mapping",
        )
    max_parallel = int(raw.get("max_parallel", 1))
    if not 1 <= max_parallel <= MAX_HANDOFF_PARALLELISM:
        raise HandoffContractError.invalid(
            path,
            "handoff max_parallel must be between 1 and 5",
        )
    values = raw.get("agents")
    if not isinstance(values, list) or not values:
        raise HandoffContractError.invalid(
            path,
            "handoff_contract agents must be a non-empty list",
        )
    agents = tuple(_parse_agent(item, path) for item in values)
    names = tuple(agent.name for agent in agents)
    if len(set(names)) != len(names):
        raise HandoffContractError.invalid(
            path,
            "handoff agent names must be unique",
        )
    known = set(names)
    for agent in agents:
        unknown = set(agent.starts_after) - known
        if unknown:
            raise HandoffContractError.invalid(
                path,
                f"{agent.name} depends on unknown agents: {', '.join(sorted(unknown))}",
            )
        if agent.name in agent.starts_after:
            raise HandoffContractError.invalid(
                path,
                f"{agent.name} cannot depend on itself",
            )
    _validate_acyclic(agents, path)
    authority = raw.get("output_authority")
    if authority is not None and authority not in known:
        raise HandoffContractError.invalid(
            path,
            "output_authority must name a declared handoff agent",
        )
    return HandoffContract(max_parallel, agents, authority)


def handoff_contract_mapping(contract: HandoffContract | None) -> dict[str, Any]:
    """Return a JSON-safe handoff contract mapping."""
    return {} if contract is None else asdict(contract)


def _parse_agent(raw: object, path: Path) -> HandoffAgentContract:
    if not isinstance(raw, dict):
        raise HandoffContractError.invalid(
            path,
            "handoff agents must be mappings",
        )
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise HandoffContractError.invalid(
            path,
            "handoff agent name must be a non-empty string",
        )
    minimum = int(raw.get("min_calls", 1))
    maximum = int(raw.get("max_calls", 1))
    if minimum < 0 or maximum < minimum:
        raise HandoffContractError.invalid(
            path,
            f"invalid call bounds for handoff agent {name}",
        )
    parent = raw.get("parent", "Orchestrator")
    if not isinstance(parent, str) or not parent.strip():
        raise HandoffContractError.invalid(
            path,
            f"parent for handoff agent {name} must be a non-empty string",
        )
    return HandoffAgentContract(
        name=name,
        parent=parent,
        min_calls=minimum,
        max_calls=maximum,
        starts_after=_strings(raw.get("starts_after", []), path),
        required_input_fields=_strings(
            raw.get("required_input_fields", []),
            path,
        ),
        required_output_fields=_strings(
            raw.get("required_output_fields", []),
            path,
        ),
        expected_mode=str(raw.get("expected_mode", "execute")),
        can_delegate=bool(raw.get("can_delegate", False)),
    )


def _strings(raw: object, path: Path) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(
        isinstance(item, str) and item.strip() for item in raw
    ):
        raise HandoffContractError.invalid(
            path,
            "handoff fields must be string lists",
        )
    return tuple(raw)


def _validate_acyclic(
    agents: tuple[HandoffAgentContract, ...],
    path: Path,
) -> None:
    dependencies = {agent.name: set(agent.starts_after) for agent in agents}
    remaining = set(dependencies)
    while remaining:
        ready = {name for name in remaining if not (dependencies[name] & remaining)}
        if not ready:
            raise HandoffContractError.invalid(
                path,
                "handoff dependencies contain a cycle",
            )
        remaining -= ready
