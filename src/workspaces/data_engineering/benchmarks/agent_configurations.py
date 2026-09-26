"""Load reusable agent configurations for benchmark evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class AgentConfigurationManifestError(ValueError):
    """Raised when an agent configuration manifest is invalid."""

    @classmethod
    def invalid(
        cls,
        path: Path,
        reason: str,
    ) -> AgentConfigurationManifestError:
        """Create an error identifying the invalid manifest."""
        return cls(f"{path}: {reason}")


@dataclass(frozen=True, slots=True)
class AgentConfigurationManifest:
    """Reusable agent and judge configurations indexed by profile."""

    configurations: tuple[dict[str, Any], ...]

    def select(self, profile: str) -> dict[str, Any]:
        """Return one registered profile or raise an actionable error."""
        for configuration in self.configurations:
            if configuration.get("profile") == profile:
                return configuration
        message = f"unknown agent configuration: {profile}"
        raise AgentConfigurationManifestError(message)

    def candidates(self) -> tuple[dict[str, Any], ...]:
        """Return all configurations eligible to run as candidates."""
        return tuple(
            configuration
            for configuration in self.configurations
            if configuration.get("role", "candidate") != "judge"
        )


def load_agent_configurations(path: Path) -> AgentConfigurationManifest:
    """Load and validate a reusable agent configuration manifest."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise AgentConfigurationManifestError.invalid(
            path,
            "schema_version must be 1",
        )
    values = raw.get("configurations")
    if not isinstance(values, list) or not values:
        raise AgentConfigurationManifestError.invalid(
            path,
            "configurations must be a non-empty list",
        )
    if not all(isinstance(value, dict) for value in values):
        raise AgentConfigurationManifestError.invalid(
            path,
            "each configuration must be a mapping",
        )
    configurations = tuple(values)
    profiles = [configuration.get("profile") for configuration in configurations]
    if len(set(profiles)) != len(profiles):
        raise AgentConfigurationManifestError.invalid(
            path,
            "configuration profiles must be unique",
        )
    return AgentConfigurationManifest(configurations)
