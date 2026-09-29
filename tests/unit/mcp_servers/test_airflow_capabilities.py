from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from adapters.mcp import airflow_failure_payload
from mcp_servers import airflow
from workspaces.data_engineering.agents.production_support import (
    AirflowFailure,
    Region,
)
from workspaces.data_engineering.agents.production_support.workloads import (
    AirflowTaskMetadata,
)


class FakeSource:
    async def discover_failures(self, since):
        del since
        return (_failure(),)

    async def discover_region_failures(self, region, since):
        assert region is Region.US_01
        del since
        return (_failure(),)

    async def fetch_log(self, failure):
        assert failure == _failure()
        return "OOMKilled"

    async def has_success_within(self, failure, start_at, end_at):
        assert failure == _failure()
        assert end_at > start_at
        return True

    async def fetch_task_metadata(self, failure):
        assert failure == _failure()
        return AirflowTaskMetadata("dag", "task", "SparkSubmitOperator")


def _failure() -> AirflowFailure:
    return AirflowFailure(
        Region.US_01,
        "dag",
        "run",
        "task",
        datetime(2026, 9, 27, 5, tzinfo=UTC),
        datetime(2026, 9, 27, 6, tzinfo=UTC),
    )


def test_airflow_server_exposes_read_only_capabilities(monkeypatch) -> None:
    monkeypatch.setattr(airflow, "_source", FakeSource)
    payload = airflow_failure_payload(_failure())

    discovered = asyncio.run(
        airflow.list_failed_task_instances(
            "2026-09-27T05:00:00Z",
            "US-01",
        )
    )
    log = asyncio.run(airflow.get_task_log(payload))
    success = asyncio.run(
        airflow.has_task_success(
            payload,
            "2026-09-27T05:00:00Z",
            "2026-09-28T05:00:00Z",
        )
    )
    metadata = asyncio.run(airflow.get_task_metadata(payload))

    assert discovered["count"] == 1
    assert log["log"] == "OOMKilled"
    assert success["has_success"] is True
    assert metadata["operator_name"] == "SparkSubmitOperator"
