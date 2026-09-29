from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from adapters.mcp import AirflowMcpError, AirflowMcpSource
from workspaces.data_engineering.agents.production_support import (
    AirflowFailure,
    Region,
)


class FakeCaller:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        failure = {
            "region": "US-01",
            "dag_id": "dag",
            "run_id": "run",
            "task_id": "task",
            "start_at": "2026-09-27T05:00:00+00:00",
            "end_at": "2026-09-27T06:00:00+00:00",
            "try_number": 1,
            "log": "",
        }
        return {
            "list_failed_task_instances": {"failures": [failure]},
            "get_task_log": {"log": "OOMKilled"},
            "has_task_success": {"has_success": True},
            "get_task_metadata": {"operator_name": "SparkSubmitOperator"},
        }[name]


def _failure() -> AirflowFailure:
    return AirflowFailure(
        Region.US_01,
        "dag",
        "run",
        "task",
        datetime(2026, 9, 27, 5, tzinfo=UTC),
        datetime(2026, 9, 27, 6, tzinfo=UTC),
    )


def test_airflow_mcp_source_implements_read_protocols() -> None:
    caller = FakeCaller()
    source = AirflowMcpSource(caller)
    cutoff = datetime(2026, 9, 27, 5, tzinfo=UTC)

    failures = asyncio.run(source.discover_region_failures(Region.US_01, cutoff))
    log = asyncio.run(source.fetch_log(failures[0]))
    recovered = asyncio.run(
        source.has_success_within(
            failures[0],
            cutoff,
            datetime(2026, 9, 28, 5, tzinfo=UTC),
        )
    )
    metadata = asyncio.run(source.fetch_task_metadata(failures[0]))

    assert failures == (_failure(),)
    assert log == "OOMKilled"
    assert recovered is True
    assert metadata.operator_name == "SparkSubmitOperator"
    assert caller.calls[0][1]["region"] == "US-01"


def test_airflow_mcp_source_rejects_invalid_results() -> None:
    class InvalidCaller:
        async def call_tool(self, name, arguments):
            del name, arguments
            return {"failures": "invalid"}

    with pytest.raises(AirflowMcpError, match="list"):
        asyncio.run(
            AirflowMcpSource(InvalidCaller()).discover_failures(
                datetime(2026, 9, 27, 5, tzinfo=UTC)
            )
        )
