from __future__ import annotations

import asyncio

from mcp_servers import oms
from workspaces.data_engineering.agents.oms_agent import OmsQueryResult


class FakeQuerySource:
    async def query(self, workspace, query):
        assert workspace.name == "pl-oms-us-primary"
        assert query.timespan == "PT5M"
        return OmsQueryResult(("message",), (("ready",),))


class FakeJobSource:
    async def query_job(self, parameters):
        assert parameters.client_id_g == "client"
        return '{"message_s": "ready"}'


def test_oms_server_exposes_read_only_queries(monkeypatch) -> None:
    monkeypatch.setattr(oms, "_query_source", FakeQuerySource)
    monkeypatch.setattr(oms, "_job_source", FakeJobSource)

    query = asyncio.run(oms.query_oms("production", "us", "Table | take 1", "PT5M"))
    evidence = asyncio.run(
        oms.query_job_evidence(
            {
                "region": "us",
                "client_id_g": "client",
                "run_id_s": "run",
                "task_id_s": "task",
                "try_number_d": 1,
                "start_at": "2026-09-27T05:00:00Z",
                "table": "DI_Scheduling_CL",
            }
        )
    )

    assert query["rows"] == [["ready"]]
    assert "ready" in evidence["evidence"]
