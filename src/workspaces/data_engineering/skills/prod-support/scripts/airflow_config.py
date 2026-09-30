"""Resolve Airflow connections from configurations.yaml for skill scripts.

Each entry under workspaces.data_engineering.airflow names the environment
variables holding its host and credentials. Every parameter is required.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ENVIRONMENTS = ("alpha", "staging", "produs", "prodca")
PRODUCTION = {"US-01": "produs", "CA-02": "prodca"}
CONFIGURATION_NAME = "configurations.yaml"
SECTION = ("workspaces", "data_engineering", "airflow")
KEYS = ("host_env", "user_env", "password_env")


class AirflowConfigError(RuntimeError):
    """Raised when an Airflow connection is not fully parameterized."""


@dataclass(frozen=True)
class AirflowEntry:
    """Variable names for one configured Airflow environment."""

    environment: str
    host_env: str
    user_env: str
    password_env: str

    def host(self) -> str:
        """Return the https:// base URL from the host variable."""
        host = _required(self.host_env, self.environment).rstrip("/")
        if not host.startswith("https://"):
            raise AirflowConfigError(
                f"{self.host_env} must be an https:// URL for Airflow {self.environment}"
            )
        return host

    def credentials(self) -> tuple[str, str]:
        """Return the basic-auth user and password."""
        return (
            _required(self.user_env, self.environment),
            _required(self.password_env, self.environment),
        )


def find_configuration(explicit: Path | None = None) -> Path:
    """Return the explicit path, or the nearest configurations.yaml upward."""
    if explicit is not None:
        if not explicit.is_file():
            raise AirflowConfigError(f"configuration does not exist: {explicit}")
        return explicit
    for directory in (Path.cwd(), *Path.cwd().parents):
        candidate = directory / CONFIGURATION_NAME
        if candidate.is_file():
            return candidate
    raise AirflowConfigError(
        f"no {CONFIGURATION_NAME} found from {Path.cwd()} upward; "
        "copy configurations.yaml.example or pass --config"
    )


def load_entry(environment: str, path: Path) -> AirflowEntry:
    """Return one environment's variable names, failing on any absent key."""
    try:
        import yaml
    except ImportError as error:
        raise AirflowConfigError("PyYAML is required; run with `uv run`") from error
    node: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    dotted = ".".join((*SECTION, environment))
    for key in (*SECTION, environment):
        node = node.get(key) if isinstance(node, dict) else None
        if not isinstance(node, dict):
            raise AirflowConfigError(f"{path}: {dotted} must be a mapping")
    names = []
    for key in KEYS:
        value = node.get(key)
        if not isinstance(value, str) or not value.strip():
            raise AirflowConfigError(f"{path}: {dotted}.{key} must be set")
        names.append(value.strip())
    return AirflowEntry(environment, *names)


def entry_for_host(hostname: str, path: Path) -> AirflowEntry:
    """Return the configured environment whose host matches a URL hostname."""
    for environment in ENVIRONMENTS:
        entry = load_entry(environment, path)
        host = os.environ.get(entry.host_env, "").strip()
        if host and host.rstrip("/").removeprefix("https://") == hostname:
            return entry
    raise AirflowConfigError(f"{hostname} matches no Airflow host in {path}")


def _required(name: str, environment: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise AirflowConfigError(
            f"Airflow {environment} needs {name}; set it in the environment or .env"
        )
    return value
