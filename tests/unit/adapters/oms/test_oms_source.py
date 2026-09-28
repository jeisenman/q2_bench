import asyncio
import base64
import json
from urllib.request import Request

import pytest

from adapters.oms import (
    AzureLogAnalyticsSource,
    OmsAdapterError,
    OmsDataCollectorSink,
)
from workspaces.data_engineering.agents.oms_agent import (
    OmsLogRecord,
    OmsQuery,
    OmsWorkspace,
)

WORKSPACE = OmsWorkspace("workspace", "workspace-id", "subscription-id")


class FakeTokenSource:
    def access_token(self, subscription_id: str) -> str:
        assert subscription_id == "subscription-id"
        return "token"


class FakeTransport:
    def __init__(self, status: int, payload: bytes = b"") -> None:
        self.status = status
        self.payload = payload
        self.requests: list[Request] = []

    def request(self, request: Request) -> tuple[int, bytes]:
        self.requests.append(request)
        return self.status, self.payload


def test_query_builds_authenticated_bounded_request() -> None:
    payload = json.dumps(
        {
            "tables": [
                {
                    "columns": [{"name": "message"}],
                    "rows": [["ready"]],
                }
            ]
        }
    ).encode()
    transport = FakeTransport(200, payload)
    source = AzureLogAnalyticsSource(FakeTokenSource(), transport)

    result = asyncio.run(source.query(WORKSPACE, OmsQuery("Table | take 1", "PT5M")))

    assert result.columns == ("message",)
    assert result.rows == (("ready",),)
    request = transport.requests[0]
    assert request.full_url.endswith("/v1/workspaces/workspace-id/query")
    assert request.get_header("Authorization") == "Bearer token"
    assert json.loads(request.data or b"") == {
        "query": "Table | take 1",
        "timespan": "PT5M",
    }


def test_query_rejects_provider_failure_and_invalid_shape() -> None:
    failed = AzureLogAnalyticsSource(FakeTokenSource(), FakeTransport(403))
    invalid = AzureLogAnalyticsSource(FakeTokenSource(), FakeTransport(200, b"{}"))

    with pytest.raises(OmsAdapterError, match="HTTP 403"):
        asyncio.run(failed.query(WORKSPACE, OmsQuery("Table", "PT5M")))
    with pytest.raises(OmsAdapterError, match="invalid shape"):
        asyncio.run(invalid.query(WORKSPACE, OmsQuery("Table", "PT5M")))


def test_log_sink_signs_and_posts_one_record() -> None:
    transport = FakeTransport(202)
    sink = OmsDataCollectorSink(
        shared_key=base64.b64encode(b"secret").decode(),
        transport=transport,
    )

    asyncio.run(sink.write(WORKSPACE, OmsLogRecord("AgentTest", {"message": "hello"})))

    request = transport.requests[0]
    assert request.full_url.startswith(
        "https://workspace-id.ods.opinsights.azure.com/api/logs"
    )
    assert request.get_header("Log-type") == "AgentTest"
    assert request.get_header("Authorization").startswith("SharedKey workspace-id:")
    assert json.loads(request.data or b"") == [{"message": "hello"}]


def test_log_sink_rejects_invalid_key_and_provider_failure() -> None:
    invalid_key = OmsDataCollectorSink("not base64!", FakeTransport(202))
    failed = OmsDataCollectorSink(
        base64.b64encode(b"secret").decode(),
        FakeTransport(500),
    )
    record = OmsLogRecord("AgentTest", {"message": "hello"})

    with pytest.raises(OmsAdapterError, match="valid base64"):
        asyncio.run(invalid_key.write(WORKSPACE, record))
    with pytest.raises(OmsAdapterError, match="HTTP 500"):
        asyncio.run(failed.write(WORKSPACE, record))
