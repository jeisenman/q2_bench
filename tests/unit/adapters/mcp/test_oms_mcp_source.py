from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from adapters.mcp import OmsMcpSource
from workspaces.data_engineering.agents.oms_agent import (
    OmsEnvironment,
    OmsJobQueryParameters,
    OmsQuery,
    OmsRegion,
    resolve_workspace,
)


class FakeCaller:
    async def call_tool(self, name, arguments):
        if name == "query_oms":
            assert arguments["environment"] == "production"
            return {"columns": ["message"], "rows": [["ready"]]}
        assert name == "query_job_evidence"
        return {"evidence": '{"message_s": "OOMKilled"}'}


def test_oms_mcp_source_queries_tables_and_exact_jobs() -> None:
    source = OmsMcpSource(FakeCaller())
    result = asyncio.run(
        source.query(
            resolve_workspace(OmsEnvironment.PRODUCTION, OmsRegion.US),
            OmsQuery("Table | take 1", "PT5M"),
        )
    )
    evidence = asyncio.run(
        source.query_job(
            OmsJobQueryParameters(
                region=OmsRegion.US,
                client_id_g="client",
                run_id_s="run",
                task_id_s="task",
                try_number_d=1,
                start_at=datetime(2026, 9, 27, 5, tzinfo=UTC),
            )
        )
    )

    assert result.columns == ("message",)
    assert result.rows == (("ready",),)
    assert "OOMKilled" in evidence
