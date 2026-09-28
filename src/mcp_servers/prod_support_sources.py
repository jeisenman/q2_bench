"""Production-support MCP source composition."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from adapters.airflow import AirflowApiSource
from adapters.codex_cli import CodexCliRuntime
from adapters.kubernetes import ClusterHealthScriptSource
from adapters.postgres import agent_memory_from_environment
from adapters.resource_discovery import (
    IndexedResourceDiscoverySource,
    JsonClientLookupSource,
    ResourceDiscoveryApiSource,
    configured_client_lookup_path,
)
from agent_memory import AgentMemory
from workspaces.data_engineering.agents.production_support import (
    AirflowFailure,
    AirflowFailureSource,
    ReplayAirflowFailureSource,
)
from workspaces.data_engineering.agents.resource_discovery import (
    ResourceDiscoveryAgent,
)

SOURCE_ENV = "PROD_SUPPORT_SOURCE"
DATASET_ENV = "PROD_SUPPORT_DATASET"


class EmptyAirflowFailureSource:
    """Safe default source when no replay dataset is configured."""

    async def discover_failures(
        self,
        since: datetime,
    ) -> tuple[AirflowFailure, ...]:
        """Return no production failures."""
        del since
        return ()

    async def fetch_log(self, failure: AirflowFailure) -> str:
        """Return the embedded log when present."""
        return failure.log


def airflow_source() -> AirflowFailureSource:
    """Select the configured production, replay, or safe empty source."""
    source_mode = os.environ.get(SOURCE_ENV)
    dataset = os.environ.get(DATASET_ENV)
    if source_mode is None:
        return (
            ReplayAirflowFailureSource(Path(dataset))
            if dataset
            else EmptyAirflowFailureSource()
        )
    if source_mode == "production":
        if dataset:
            message = f"{DATASET_ENV} cannot be set when {SOURCE_ENV}=production"
            raise ValueError(message)
        return AirflowApiSource.from_environment()
    if source_mode == "replay":
        if not dataset:
            message = f"{DATASET_ENV} is required when {SOURCE_ENV}=replay"
            raise ValueError(message)
        return ReplayAirflowFailureSource(Path(dataset))
    if source_mode == "empty":
        if dataset:
            message = f"{DATASET_ENV} cannot be set when {SOURCE_ENV}=empty"
            raise ValueError(message)
        return EmptyAirflowFailureSource()
    message = (
        f"unsupported {SOURCE_ENV} value {source_mode!r}; "
        "expected production, replay, or empty"
    )
    raise ValueError(message)


def resource_discovery() -> ResourceDiscoveryAgent | None:
    """Select genuine Resource Discovery only for explicit production mode."""
    if os.environ.get(SOURCE_ENV) != "production":
        return None
    source = IndexedResourceDiscoverySource(
        ResourceDiscoveryApiSource.from_environment(),
        JsonClientLookupSource(configured_client_lookup_path()),
    )
    return ResourceDiscoveryAgent(
        source,
        memory=agent_memory_from_environment("resource-discovery"),
    )


def memory() -> AgentMemory | None:
    """Return scoped durable memory for production-support summaries."""
    if os.environ.get(SOURCE_ENV) != "production":
        return None
    return agent_memory_from_environment("production-support")


def report_runtime() -> CodexCliRuntime | None:
    """Use the configured Bedrock-backed Codex runtime in production."""
    if os.environ.get(SOURCE_ENV) != "production":
        return None
    return CodexCliRuntime()


def cluster_health() -> ClusterHealthScriptSource | None:
    """Use the read-only cluster script only for explicit production mode."""
    if os.environ.get(SOURCE_ENV) != "production":
        return None
    return ClusterHealthScriptSource.from_repository()
