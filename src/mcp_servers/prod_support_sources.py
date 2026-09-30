"""Production-support MCP source composition."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import cast

from adapters.airflow import AirflowApiSource
from adapters.kubernetes import ClusterHealthScriptSource
from adapters.mcp import (
    AirflowMcpSource,
    OmsMcpSource,
    ResourceDiscoveryMcpSource,
    project_stdio_caller,
)
from adapters.oms import AzureOmsJobEvidenceSource
from adapters.postgres import agent_memory_from_environment
from adapters.resource_discovery import (
    IndexedResourceDiscoverySource,
    JsonClientLookupSource,
    ResourceDiscoveryApiSource,
    configured_client_lookup_path,
)
from agent_memory import AgentMemory
from workspaces.data_engineering.agents.resource_discovery import (
    ResourceDiscoveryAgent,
)
from workspaces.data_engineering.workflows.prod_support import (
    AirflowFailure,
    AirflowFailureSource,
    AirflowTaskMetadataSource,
    OmsJobEvidenceSource,
    ReplayAirflowFailureSource,
)

SOURCE_ENV = "PROD_SUPPORT_SOURCE"
DATASET_ENV = "PROD_SUPPORT_DATASET"
DIRECT_MODE = "direct"
MCP_MODE = "mcp"
REPLAY_MODE = "replay"
EMPTY_MODE = "empty"
LIVE_MODES = frozenset({DIRECT_MODE, MCP_MODE})


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
    """Select direct, MCP, replay, or safe-empty Airflow capabilities."""
    source_mode = _source_mode()
    dataset = os.environ.get(DATASET_ENV)
    if source_mode == DIRECT_MODE:
        if dataset:
            message = f"{DATASET_ENV} cannot be set when {SOURCE_ENV}={DIRECT_MODE}"
            raise ValueError(message)
        return AirflowApiSource.from_configuration()
    if source_mode == MCP_MODE:
        if dataset:
            message = f"{DATASET_ENV} cannot be set when {SOURCE_ENV}=mcp"
            raise ValueError(message)
        return AirflowMcpSource(project_stdio_caller("airflow-mcp"))
    if source_mode == REPLAY_MODE:
        if not dataset:
            message = f"{DATASET_ENV} is required when {SOURCE_ENV}=replay"
            raise ValueError(message)
        return ReplayAirflowFailureSource(Path(dataset))
    if source_mode == EMPTY_MODE:
        if dataset:
            message = f"{DATASET_ENV} cannot be set when {SOURCE_ENV}=empty"
            raise ValueError(message)
        return EmptyAirflowFailureSource()
    message = (
        f"unsupported {SOURCE_ENV} value {source_mode!r}; "
        "expected direct, mcp, replay, or empty"
    )
    raise ValueError(message)


def resource_discovery() -> ResourceDiscoveryAgent | None:
    """Select direct or MCP Resource Discovery for live modes."""
    source_mode = _source_mode()
    if source_mode not in LIVE_MODES:
        return None
    source = (
        IndexedResourceDiscoverySource(
            ResourceDiscoveryApiSource.from_environment(),
            JsonClientLookupSource(configured_client_lookup_path()),
        )
        if source_mode == DIRECT_MODE
        else ResourceDiscoveryMcpSource(project_stdio_caller("resource-discovery-mcp"))
    )
    return ResourceDiscoveryAgent(
        source,
        memory=agent_memory_from_environment("resource-discovery"),
    )


def airflow_task_metadata(
    source: AirflowFailureSource,
) -> AirflowTaskMetadataSource | None:
    """Return task metadata when the selected Airflow capability supports it."""
    if not hasattr(source, "fetch_task_metadata"):
        return None
    return cast("AirflowTaskMetadataSource", source)


def oms_evidence() -> OmsJobEvidenceSource | None:
    """Select direct or MCP exact-job OMS evidence for live modes."""
    source_mode = _source_mode()
    if source_mode == DIRECT_MODE:
        return AzureOmsJobEvidenceSource.create()
    if source_mode == MCP_MODE:
        return OmsMcpSource(project_stdio_caller("remote-data-mcp"))
    return None


def memory() -> AgentMemory | None:
    """Return scoped durable memory for production-support summaries."""
    if _source_mode() not in LIVE_MODES:
        return None
    return agent_memory_from_environment("production-support")


def cluster_health() -> ClusterHealthScriptSource | None:
    """Use the read-only cluster script for direct and MCP live modes."""
    if _source_mode() not in LIVE_MODES:
        return None
    return ClusterHealthScriptSource.from_repository()


def _source_mode() -> str:
    configured = os.environ.get(SOURCE_ENV)
    if configured == "production":
        return DIRECT_MODE
    if configured is not None:
        return configured
    return REPLAY_MODE if os.environ.get(DATASET_ENV) else EMPTY_MODE
