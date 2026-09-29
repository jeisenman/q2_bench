"""Airflow capability adapter backed by read-only MCP tools."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from adapters.mcp.client import McpToolCaller
from workspaces.data_engineering.agents.production_support import (
    AirflowFailure,
    Region,
)
from workspaces.data_engineering.agents.production_support.workloads import (
    AirflowTaskMetadata,
)


class AirflowMcpError(RuntimeError):
    """Raised when an Airflow MCP result violates its typed contract."""

    @classmethod
    def invalid_log(cls) -> AirflowMcpError:
        """Return an error for a malformed task log."""
        return cls("Airflow MCP task log must be text")

    @classmethod
    def invalid_success(cls) -> AirflowMcpError:
        """Return an error for a malformed recovery result."""
        return cls("Airflow MCP success result must be boolean")

    @classmethod
    def invalid_operator(cls) -> AirflowMcpError:
        """Return an error for malformed task metadata."""
        return cls("Airflow MCP operator_name must be text")

    @classmethod
    def invalid_failures(cls) -> AirflowMcpError:
        """Return an error for a malformed failure collection."""
        return cls("Airflow MCP failures must be a list")

    @classmethod
    def invalid_failure_object(cls) -> AirflowMcpError:
        """Return an error for a non-object failure item."""
        return cls("Airflow MCP failure must be an object")

    @classmethod
    def invalid_failure(cls) -> AirflowMcpError:
        """Return an error for a malformed failure payload."""
        return cls("invalid Airflow MCP failure payload")

    @classmethod
    def timezone_required(cls) -> AirflowMcpError:
        """Return an error for a naive MCP timestamp."""
        return cls("MCP timestamps must be timezone-aware")


class AirflowMcpSource:
    """Implement production-support Airflow read protocols through MCP."""

    def __init__(self, caller: McpToolCaller) -> None:
        """Initialize with an injected MCP tool caller."""
        self._caller = caller

    async def discover_failures(
        self,
        since: datetime,
    ) -> tuple[AirflowFailure, ...]:
        """Return failures across all configured regions."""
        result = await self._caller.call_tool(
            "list_failed_task_instances",
            {"since": _timestamp(since)},
        )
        return _failures(result)

    async def discover_region_failures(
        self,
        region: Region,
        since: datetime,
    ) -> tuple[AirflowFailure, ...]:
        """Return failures for one explicit region."""
        result = await self._caller.call_tool(
            "list_failed_task_instances",
            {"since": _timestamp(since), "region": region.value},
        )
        return _failures(result)

    async def fetch_log(self, failure: AirflowFailure) -> str:
        """Return the exact log for one failed task attempt."""
        result = await self._caller.call_tool(
            "get_task_log",
            {"failure": airflow_failure_payload(failure)},
        )
        log = result.get("log")
        if not isinstance(log, str):
            raise AirflowMcpError.invalid_log()
        return log

    async def has_success_within(
        self,
        failure: AirflowFailure,
        start_at: datetime,
        end_at: datetime,
    ) -> bool:
        """Return whether the exact DAG and task succeeded in the window."""
        result = await self._caller.call_tool(
            "has_task_success",
            {
                "failure": airflow_failure_payload(failure),
                "start_at": _timestamp(start_at),
                "end_at": _timestamp(end_at),
            },
        )
        recovered = result.get("has_success")
        if not isinstance(recovered, bool):
            raise AirflowMcpError.invalid_success()
        return recovered

    async def fetch_task_metadata(
        self,
        failure: AirflowFailure,
    ) -> AirflowTaskMetadata:
        """Return exact task operator metadata."""
        result = await self._caller.call_tool(
            "get_task_metadata",
            {"failure": airflow_failure_payload(failure)},
        )
        operator_name = result.get("operator_name")
        if not isinstance(operator_name, str):
            raise AirflowMcpError.invalid_operator()
        return AirflowTaskMetadata(
            dag_id=failure.dag_id,
            task_id=failure.task_id,
            operator_name=operator_name,
        )


def airflow_failure_payload(failure: AirflowFailure) -> dict[str, object]:
    """Serialize one failure for a read-only MCP request."""
    return {
        "region": failure.region.value,
        "dag_id": failure.dag_id,
        "run_id": failure.run_id,
        "task_id": failure.task_id,
        "start_at": _timestamp(failure.start_at),
        "end_at": _timestamp(failure.end_at),
        "try_number": failure.try_number,
        "log": failure.log,
    }


def airflow_failure_from_payload(value: Mapping[str, object]) -> AirflowFailure:
    """Validate and deserialize one Airflow MCP failure payload."""
    try:
        return AirflowFailure(
            region=Region(str(value["region"])),
            dag_id=str(value["dag_id"]),
            run_id=str(value["run_id"]),
            task_id=str(value["task_id"]),
            start_at=_datetime(value["start_at"]),
            end_at=_datetime(value["end_at"]),
            try_number=int(str(value["try_number"])),
            log=str(value.get("log", "")),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise AirflowMcpError.invalid_failure() from error


def _failures(result: Mapping[str, object]) -> tuple[AirflowFailure, ...]:
    values = result.get("failures")
    if not isinstance(values, list):
        raise AirflowMcpError.invalid_failures()
    failures = []
    for value in values:
        if not isinstance(value, Mapping):
            raise AirflowMcpError.invalid_failure_object()
        failures.append(airflow_failure_from_payload(value))
    return tuple(failures)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise AirflowMcpError.timezone_required()
    return value.isoformat()


def _datetime(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise AirflowMcpError.timezone_required()
    return parsed
