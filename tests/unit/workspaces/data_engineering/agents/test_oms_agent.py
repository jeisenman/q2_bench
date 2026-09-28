import asyncio

import pytest

from domain import AgentRequest
from workspaces.data_engineering.agents.oms_agent import (
    OmsAgent,
    OmsAgentError,
    OmsEnvironment,
    OmsLogRecord,
    OmsQuery,
    OmsQueryResult,
    OmsRegion,
    OmsWorkspaceError,
    resolve_workspace,
)


class FakeQuerySource:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []

    async def query(self, workspace: object, query: object) -> OmsQueryResult:
        self.calls.append((workspace, query))
        return OmsQueryResult(("message",), (("ready",),))


class FakeLogSink:
    def __init__(self) -> None:
        self.calls: list[tuple[object, OmsLogRecord]] = []

    async def write(self, workspace: object, record: OmsLogRecord) -> None:
        self.calls.append((workspace, record))


def test_workspace_routes_match_di_scheduling_datastores() -> None:
    production_us = resolve_workspace(OmsEnvironment.PRODUCTION, OmsRegion.US)
    production_ca = resolve_workspace(OmsEnvironment.PRODUCTION, OmsRegion.CA)
    staging = resolve_workspace(OmsEnvironment.STAGING, OmsRegion.US)
    development = resolve_workspace(OmsEnvironment.DEVELOPMENT, OmsRegion.US)

    assert production_us.name == "pl-oms-us-primary"
    assert production_ca.name == "pl-oms-ca-primary"
    assert staging.name == "pl-oms-preprod-primary"
    assert development == staging


def test_workspace_rejects_unsupported_nonproduction_canada_route() -> None:
    with pytest.raises(OmsWorkspaceError, match="no OMS workspace"):
        resolve_workspace(OmsEnvironment.STAGING, OmsRegion.CA)


def test_query_returns_deterministic_agent_result() -> None:
    source = FakeQuerySource()
    agent = OmsAgent(source, FakeLogSink())
    request = AgentRequest(
        "Heartbeat_CL | take 1",
        "query-1",
        (
            ("operation", "query"),
            ("environment", "staging"),
            ("region", "us"),
            ("timespan", "PT15M"),
        ),
    )

    result = asyncio.run(agent.run(request))

    assert result.output == '{"columns": ["message"], "rows": [["ready"]]}'
    assert result.tool_calls == ("QueryOms",)
    assert ("workspace", "pl-oms-preprod-primary") in result.attributes
    assert len(source.calls) == 1


def test_writes_are_disabled_by_default() -> None:
    agent = OmsAgent(FakeQuerySource(), FakeLogSink())

    with pytest.raises(OmsAgentError, match="writes are disabled"):
        asyncio.run(
            agent.write_log(
                OmsEnvironment.STAGING,
                OmsRegion.US,
                OmsLogRecord("AgentTest", {"message": "test"}),
            )
        )


def test_staging_write_uses_injected_sink_when_enabled() -> None:
    sink = FakeLogSink()
    agent = OmsAgent(FakeQuerySource(), sink, allow_writes=True)

    asyncio.run(
        agent.write_log(
            OmsEnvironment.STAGING,
            OmsRegion.US,
            OmsLogRecord("AgentTest", {"message": "test"}),
        )
    )

    assert len(sink.calls) == 1


def test_production_write_requires_separate_authorization() -> None:
    agent = OmsAgent(FakeQuerySource(), FakeLogSink(), allow_writes=True)

    with pytest.raises(OmsAgentError, match="production OMS writes"):
        asyncio.run(
            agent.write_log(
                OmsEnvironment.PRODUCTION,
                OmsRegion.US,
                OmsLogRecord("AgentTest", {"message": "test"}),
            )
        )


@pytest.mark.parametrize(
    ("attributes", "message"),
    [
        (
            (
                ("operation", "query"),
                ("environment", "invalid"),
                ("region", "us"),
                ("timespan", "PT15M"),
            ),
            "environment must be one of",
        ),
        (
            (
                ("operation", "invalid"),
                ("environment", "staging"),
                ("region", "us"),
            ),
            "operation must be",
        ),
    ],
)
def test_run_rejects_invalid_requests(
    attributes: tuple[tuple[str, str], ...],
    message: str,
) -> None:
    agent = OmsAgent(FakeQuerySource(), FakeLogSink())

    with pytest.raises(OmsAgentError, match=message):
        asyncio.run(AgentRunner(agent).run(attributes))


class AgentRunner:
    def __init__(self, agent: OmsAgent) -> None:
        self.agent = agent

    async def run(self, attributes: tuple[tuple[str, str], ...]) -> object:
        return await self.agent.run(AgentRequest("request", "invalid", attributes))


def test_models_reject_empty_query_and_log_payload() -> None:
    with pytest.raises(ValueError, match="kql must not be empty"):
        OmsQuery(" ", "PT15M")
    with pytest.raises(ValueError, match="fields must not be empty"):
        OmsLogRecord("AgentTest", {})
    with pytest.raises(ValueError, match="letters, numbers, or underscores"):
        OmsLogRecord("bad-type", {"message": "test"})
