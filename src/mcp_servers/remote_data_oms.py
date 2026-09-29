"""Execute read-only OMS queries for the remote-data MCP server."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Any

from adapters.oms import AzureLogAnalyticsSource, AzureOmsJobEvidenceSource
from workspaces.data_engineering.agents.oms_agent import (
    OmsEnvironment,
    OmsJobQueryParameters,
    OmsQuery,
    OmsRegion,
    resolve_workspace,
)


class RemoteDataOmsError(ValueError):
    """Raised when an OMS query request is malformed."""

    @classmethod
    def timezone_required(cls) -> RemoteDataOmsError:
        """Return an error for a naive exact-job timestamp."""
        return cls("timezone required")


@lru_cache(maxsize=1)
def query_source() -> AzureLogAnalyticsSource:
    """Return the process-local Log Analytics query source."""
    return AzureLogAnalyticsSource.create()


@lru_cache(maxsize=1)
def job_source() -> AzureOmsJobEvidenceSource:
    """Return the process-local exact-job evidence source."""
    return AzureOmsJobEvidenceSource(query_source())


async def execute_oms_query(
    environment: str,
    region: str,
    kql: str,
    timespan: str,
) -> dict[str, object]:
    """Run bounded KQL and return JSON-compatible tabular results."""
    workspace = resolve_workspace(OmsEnvironment(environment), OmsRegion(region))
    result = await query_source().query(workspace, OmsQuery(kql, timespan))
    return {
        "workspace": workspace.name,
        "columns": list(result.columns),
        "rows": [[_json_value(value) for value in row] for row in result.rows],
    }


async def execute_job_evidence(parameters: dict[str, Any]) -> dict[str, object]:
    """Run one exact production workload query without classifying its result."""
    query_parameters = OmsJobQueryParameters(
        region=str(parameters["region"]),
        client_id_g=str(parameters["client_id_g"]),
        run_id_s=str(parameters["run_id_s"]),
        task_id_s=str(parameters["task_id_s"]),
        try_number_d=int(str(parameters["try_number_d"])),
        start_at=_datetime(str(parameters["start_at"])),
        table=str(parameters["table"]),
    )
    return {"evidence": await job_source().query_job(query_parameters)}


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise RemoteDataOmsError.timezone_required()
    return parsed


def _json_value(value: object) -> object:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)
