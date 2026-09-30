"""Resolve Airflow connections from configurations.yaml and the environment."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from adapters.local.configuration import (
    DEFAULT_CONFIGURATION_PATH,
    load_configuration,
)
from workspaces.data_engineering.workflows.prod_support.models import Region

AIRFLOW_SECTION = ("workspaces", "data_engineering", "airflow")
CONNECTION_KEYS = ("host_env", "user_env", "password_env")


class AirflowEnvironment(StrEnum):
    """Airflow deployments named in configurations.yaml."""

    ALPHA = "alpha"
    STAGING = "staging"
    PRODUS = "produs"
    PRODCA = "prodca"


PRODUCTION_ENVIRONMENTS: Mapping[Region, AirflowEnvironment] = {
    Region.US_01: AirflowEnvironment.PRODUS,
    Region.CA_02: AirflowEnvironment.PRODCA,
}


class AirflowConfigurationError(ValueError):
    """Raised when an Airflow connection is not fully parameterized."""


@dataclass(frozen=True, slots=True)
class AirflowConnection:
    """Resolved host and credentials for one Airflow deployment."""

    environment: AirflowEnvironment
    host: str
    username: str
    password: str


def load_airflow_connection(
    environment: AirflowEnvironment,
    path: Path = DEFAULT_CONFIGURATION_PATH,
    environ: Mapping[str, str] | None = None,
) -> AirflowConnection:
    """Resolve one environment, failing on any absent parameter or value."""
    values = os.environ if environ is None else environ
    entry = _environment_entry(load_configuration(path), environment, path)
    names = {
        key: _variable_name(entry, key, environment, path) for key in CONNECTION_KEYS
    }
    resolved = {key: values.get(name, "").strip() for key, name in names.items()}
    missing = sorted(names[key] for key, value in resolved.items() if not value)
    if missing:
        message = (
            f"Airflow {environment} needs environment variables "
            f"{', '.join(missing)}; set them in .env"
        )
        raise AirflowConfigurationError(message)
    host = resolved["host_env"].rstrip("/")
    if not host.startswith("https://"):
        message = (
            f"{names['host_env']} must be an https:// URL for Airflow {environment}"
        )
        raise AirflowConfigurationError(message)
    return AirflowConnection(
        environment,
        host,
        resolved["user_env"],
        resolved["password_env"],
    )


def _environment_entry(
    configuration: Mapping[str, object],
    environment: AirflowEnvironment,
    path: Path,
) -> Mapping[str, object]:
    node: Mapping[str, object] = configuration
    for key in (*AIRFLOW_SECTION, environment.value):
        child = node.get(key)
        if not isinstance(child, Mapping):
            dotted = ".".join((*AIRFLOW_SECTION, environment.value))
            message = (
                f"{path}: {dotted} must be a mapping; "
                "copy it from configurations.yaml.example"
            )
            raise AirflowConfigurationError(message)
        node = child
    return node


def _variable_name(
    entry: Mapping[str, object],
    key: str,
    environment: AirflowEnvironment,
    path: Path,
) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        dotted = ".".join((*AIRFLOW_SECTION, environment.value, key))
        message = f"{path}: {dotted} must be set"
        raise AirflowConfigurationError(message)
    return value.strip()
