"""Submit reviewed SOURCE notebooks to approved Databricks workspaces."""

from __future__ import annotations

import base64
import hashlib
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs, workspace

from adapters.local.configuration import (
    DEFAULT_CONFIGURATION_PATH,
    load_configuration,
)
from adapters.outbound.data_engineering import DATABRICKS_TARGETS

MAX_NOTEBOOK_BYTES = 1_000_000
MAX_RUN_TIMEOUT_SECONDS = 86_400
PLATFORM_CONFIGURATION_KEYS = {
    "data_engineering": "de",
    "ra": "ra",
}
REQUIRED_CONNECTION_KEYS = ("host_env", "token_env")


class DatabricksRunError(ValueError):
    """Raised when a Databricks run is unsafe or cannot be configured."""


@dataclass(frozen=True, slots=True)
class DatabricksRunRequest:
    """Reviewed notebook source and bounded one-time run settings."""

    platform: str
    source: str
    source_sha256: str
    existing_cluster_id: str
    run_name: str = "remote-data-mcp"
    timeout_seconds: int = 3_600


@dataclass(frozen=True, slots=True)
class SubmittedDatabricksRun:
    """Identifiers for one submitted Databricks notebook run."""

    target: str
    notebook_path: str
    run_id: int
    source_sha256: str


@dataclass(frozen=True, slots=True)
class DatabricksConnection:
    """Resolved credentials for one enabled Databricks workspace."""

    host: str
    token: str


class DatabricksRunClient(Protocol):
    """Provider boundary used to import and submit one notebook."""

    def workspace_id(self) -> int:
        """Return the authenticated workspace ID."""

    def import_source(self, path: str, source: str) -> None:
        """Import a Python SOURCE notebook at the requested path."""

    def submit(
        self,
        *,
        notebook_path: str,
        existing_cluster_id: str,
        run_name: str,
        timeout_seconds: int,
    ) -> int:
        """Submit the notebook and return its parent run ID."""


class SdkDatabricksRunClient:
    """Databricks SDK implementation of the run client."""

    def __init__(self, connection: DatabricksConnection) -> None:
        """Create an explicitly credentialed workspace client."""
        self._client = WorkspaceClient(
            host=connection.host,
            token=connection.token,
            auth_type="pat",
            product="q2-bench",
        )

    def workspace_id(self) -> int:
        """Return the authenticated workspace ID."""
        return self._client.get_workspace_id()

    def import_source(self, path: str, source: str) -> None:
        """Import a Python SOURCE notebook."""
        content = base64.b64encode(source.encode()).decode()
        self._client.workspace.import_(
            path,
            content=content,
            format=workspace.ImportFormat.SOURCE,
            language=workspace.Language.PYTHON,
            overwrite=True,
        )

    def submit(
        self,
        *,
        notebook_path: str,
        existing_cluster_id: str,
        run_name: str,
        timeout_seconds: int,
    ) -> int:
        """Submit a one-time notebook run without waiting for completion."""
        waiter = self._client.jobs.submit(
            idempotency_token=uuid4().hex,
            run_name=run_name,
            tasks=[
                jobs.SubmitTask(
                    task_key="remote_data",
                    existing_cluster_id=existing_cluster_id,
                    notebook_task=jobs.NotebookTask(
                        notebook_path=notebook_path,
                        source=jobs.Source.WORKSPACE,
                    ),
                )
            ],
            timeout_seconds=timeout_seconds,
        )
        return int(waiter.run_id)


DatabricksClientFactory = Callable[[DatabricksConnection], DatabricksRunClient]


def submit_databricks_run(
    request: DatabricksRunRequest,
    *,
    configuration_path: Path = DEFAULT_CONFIGURATION_PATH,
    environ: Mapping[str, str] | None = None,
    client_factory: DatabricksClientFactory = SdkDatabricksRunClient,
) -> SubmittedDatabricksRun:
    """Import and submit an exact reviewed notebook to an approved workspace."""
    normalized = request.platform.strip().lower()
    try:
        target = DATABRICKS_TARGETS[normalized]
        configuration_key = PLATFORM_CONFIGURATION_KEYS[normalized]
    except KeyError as error:
        allowed = ", ".join(sorted(DATABRICKS_TARGETS))
        message = f"platform must be one of: {allowed}"
        raise DatabricksRunError(message) from error

    digest = _validate_source(request.source, request.source_sha256)
    cluster_id = _required_text(request.existing_cluster_id, "existing_cluster_id")
    resolved_run_name = _required_text(request.run_name, "run_name")
    if not 1 <= request.timeout_seconds <= MAX_RUN_TIMEOUT_SECONDS:
        message = f"timeout_seconds must be between 1 and {MAX_RUN_TIMEOUT_SECONDS}"
        raise DatabricksRunError(message)

    connection = _load_connection(
        configuration_key,
        configuration_path,
        os.environ if environ is None else environ,
    )
    client = client_factory(connection)
    actual_workspace_id = str(client.workspace_id())
    if actual_workspace_id != target.workspace_id:
        message = (
            f"{request.platform} credentials resolved workspace "
            f"{actual_workspace_id}; "
            f"expected {target.workspace_id} ({target.name})"
        )
        raise DatabricksRunError(message)

    notebook_path = f"/Shared/remote-data-mcp/{normalized}/{digest}"
    client.import_source(notebook_path, request.source)
    run_id = client.submit(
        notebook_path=notebook_path,
        existing_cluster_id=cluster_id,
        run_name=resolved_run_name,
        timeout_seconds=request.timeout_seconds,
    )
    return SubmittedDatabricksRun(
        target=target.name,
        notebook_path=notebook_path,
        run_id=run_id,
        source_sha256=digest,
    )


def _validate_source(source: str, expected_sha256: str) -> str:
    if not source.startswith("# Databricks notebook source"):
        message = (
            "source must be a Databricks SOURCE notebook generated and reviewed "
            "before submission"
        )
        raise DatabricksRunError(message)
    source_bytes = source.encode()
    if len(source_bytes) > MAX_NOTEBOOK_BYTES:
        message = f"source must be at most {MAX_NOTEBOOK_BYTES} UTF-8 bytes"
        raise DatabricksRunError(message)
    digest = hashlib.sha256(source_bytes).hexdigest()
    if expected_sha256.strip().lower() != digest:
        message = (
            "source_sha256 does not match source; review the exact source and "
            "pass the digest returned by make_databricks_notebook"
        )
        raise DatabricksRunError(message)
    return digest


def _load_connection(
    configuration_key: str,
    path: Path,
    environ: Mapping[str, str],
) -> DatabricksConnection:
    configuration = load_configuration(path)
    workspace_entry = _mapping_at(
        configuration,
        ("workspaces", "data_engineering"),
        path,
    )
    environment_entry = _mapping_at(
        workspace_entry,
        ("databricks", configuration_key),
        path,
    )
    if workspace_entry.get("enabled") is not True:
        message = f"{path}: workspaces.data_engineering.enabled must be true"
        raise DatabricksRunError(message)
    if environment_entry.get("enabled") is not True:
        dotted = f"workspaces.data_engineering.databricks.{configuration_key}.enabled"
        message = f"{path}: {dotted} must be true"
        raise DatabricksRunError(message)
    if environment_entry.get("auth") != "pat":
        message = f"{path}: Databricks {configuration_key} auth must be pat"
        raise DatabricksRunError(message)
    ambiguous = tuple(
        name
        for name in (
            "DATABRICKS_HOST",
            "DATABRICKS_TOKEN",
            "DATABRICKS_WORKSPACE_ID",
        )
        if environ.get(name)
    )
    if ambiguous:
        message = (
            f"remove ambiguous {', '.join(ambiguous)} variables; "
            "use the environment-specific variables in configurations.yaml"
        )
        raise DatabricksRunError(message)

    variable_names = {
        key: _configuration_text(environment_entry, key, configuration_key, path)
        for key in REQUIRED_CONNECTION_KEYS
    }
    values = {
        key: environ.get(variable_name, "").strip()
        for key, variable_name in variable_names.items()
    }
    missing = [variable_names[key] for key, value in values.items() if not value]
    if missing:
        message = (
            f"Databricks {configuration_key} needs environment variables "
            f"{', '.join(sorted(missing))}"
        )
        raise DatabricksRunError(message)
    host = values["host_env"].rstrip("/")
    if not host.startswith("https://"):
        message = f"{variable_names['host_env']} must be an https:// URL"
        raise DatabricksRunError(message)
    return DatabricksConnection(host=host, token=values["token_env"])


def _mapping_at(
    root: Mapping[str, object],
    keys: tuple[str, ...],
    path: Path,
) -> Mapping[str, object]:
    current = root
    traversed: list[str] = []
    for key in keys:
        traversed.append(key)
        value = current.get(key)
        if not isinstance(value, Mapping):
            message = f"{path}: {'.'.join(traversed)} must be a mapping"
            raise DatabricksRunError(message)
        current = value
    return current


def _configuration_text(
    entry: Mapping[str, object],
    key: str,
    configuration_key: str,
    path: Path,
) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        dotted = f"workspaces.data_engineering.databricks.{configuration_key}.{key}"
        message = f"{path}: {dotted} must be set"
        raise DatabricksRunError(message)
    return value.strip()


def _required_text(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        message = f"{label} must not be empty"
        raise DatabricksRunError(message)
    return normalized
