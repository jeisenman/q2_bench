"""Session protocol, selected telemetry, redaction and persisted-state checks."""

import json
from pathlib import Path

import pytest
from test_api import Client

from semantic_api.app import create_app
from semantic_api.session_events import otel_events, redact

BASE = "/api/research/v1/sessions"
START = {
    "model": "gpt-6.1-sol",
    "cwd": "/tmp/project",
    "codex_home": "/Users/test/.codex",
    "codex_binary": "/tmp/codex",
}
AT = "2026-11-18T17:00:00Z"


def otlp(*records):
    return {
        "resourceLogs": [
            {
                "scopeLogs": [
                    {
                        "logRecords": [
                            {
                                "attributes": [
                                    {"key": key, "value": {"stringValue": value}}
                                    for key, value in record.items()
                                ]
                            }
                            for record in records
                        ]
                    }
                ]
            }
        ]
    }


@pytest.fixture
def setup(tmp_path):
    client = Client(tmp_path)
    http = create_app(client).test_client()
    response = http.post(BASE, json=START)
    assert response.status_code == 201
    return client, http, response.json


def test_selected_native_messages_redaction_dedup_restart(setup):
    client, http, record = setup
    endpoint = f"{BASE}/{record['session_id']}"
    secret = "sk-proj-CANARYcredential123456"
    body = otlp(
        {
            "event.name": "codex.user_prompt",
            "event.timestamp": AT,
            "prompt": f"Use token=CANARY_TOKEN and {secret}",
            "user.email": "private@example.test",
        },
        {
            "event.name": "codex.agent_response",
            "event.timestamp": AT,
            "response": "The answer is 24.",
            "agent.type": "main",
            "item.id": "one",
        },
        {
            "event.name": "codex.tool_result",
            "event.timestamp": AT,
            "tool_name": "shell",
            "success": "true",
            "arguments": "PRIVATE_ARGUMENTS",
            "output": "PRIVATE_OUTPUT",
        },
        {
            "event.name": "codex.reasoning",
            "event.timestamp": AT,
            "text": "PRIVATE_REASONING",
        },
        {
            "event.name": "codex.agent_response",
            "event.timestamp": AT,
            "response": "PRIVATE_SUBAGENT",
            "agent.type": "subagent",
        },
    )
    result = http.post(endpoint + "/otel", json=body)
    assert result.status_code == 200 and result.json == {
        "accepted": 3,
        "ignored": 2,
        "event_count": 3,
    }
    assert http.post(endpoint + "/otel", json=body).json["accepted"] == 0
    reopened = create_app(client).test_client().get(endpoint).json
    assert reopened["event_count"] == 3 and reopened["message_count"] == 2
    assert reopened["events"][2]["text"] is None
    persisted = json.dumps(list(client.artifacts.values()))
    for excluded in (
        secret,
        "CANARY_TOKEN",
        "PRIVATE_ARGUMENTS",
        "PRIVATE_OUTPUT",
        "PRIVATE_REASONING",
        "PRIVATE_SUBAGENT",
        "private@example.test",
    ):
        assert excluded not in persisted
    summary = http.get(BASE + "?order=oldest").json["sessions"][0]
    assert "events" not in summary and summary["event_count"] == 3
    health = http.get("/health").json
    assert health["capabilities"] == [
        "research",
        "sessions",
        "proposals",
        "documents",
        "chats",
    ]
    assert (
        health["project_root"] == str(Path(__file__).resolve().parents[2])
        and health["experiment_id"] == "1"
    )


def test_launcher_and_terminal_contract(setup):
    client, http, record = setup
    endpoint = f"{BASE}/{record['session_id']}"
    lifecycle = {
        "event_id": "start",
        "at": AT,
        "kind": "lifecycle",
        "text": "Started native Codex",
        "tool_name": None,
        "status": "started",
    }
    assert (
        http.post(endpoint + "/events", json={"events": [lifecycle]}).json["accepted"]
        == 1
    )
    assert (
        http.post(endpoint + "/events", json={"events": [lifecycle]}).json["accepted"]
        == 0
    )
    assert (
        http.post(
            endpoint + "/events", json={"events": [{**lifecycle, "text": "changed"}]}
        ).status_code
        == 409
    )
    assert (
        http.post(
            endpoint + "/events",
            json={"events": [{**lifecycle, "kind": "assistant_message"}]},
        ).status_code
        == 400
    )
    closed = {"status": "FAILED", "exit_code": 1, "error": "authorization=CANARY_ERROR"}
    done = http.post(endpoint + "/close", json=closed)
    assert done.status_code == 200 and done.json["trace_id"]
    assert "CANARY_ERROR" not in json.dumps(list(client.artifacts.values()))
    assert http.post(endpoint + "/close", json=closed).json == done.json
    assert (
        http.post(endpoint + "/close", json={**closed, "exit_code": 2}).status_code
        == 409
    )
    assert (
        http.post(endpoint + "/events", json={"events": [lifecycle]}).status_code == 409
    )
    assert create_app(client).test_client().get(endpoint).json == done.json


def test_session_boundaries(setup):
    _client, http, record = setup
    endpoint = f"{BASE}/{record['session_id']}"
    assert http.post(BASE, json={**START, "cwd": "relative"}).status_code == 400
    assert http.get(BASE + "?order=wrong").status_code == 400
    assert http.get(BASE + "/unknown").status_code == 404
    assert (
        http.post(endpoint + "/otel", json={"resourceLogs": "invalid"}).status_code
        == 400
    )
    event = {
        "event_id": "start",
        "at": "not-time",
        "kind": "lifecycle",
        "text": None,
        "tool_name": None,
        "status": None,
    }
    assert http.post(endpoint + "/events", json={"events": [event]}).status_code == 400
    assert (
        http.post(
            endpoint + "/close",
            json={"status": "CLOSED", "exit_code": True, "error": None},
        ).status_code
        == 400
    )
    with pytest.raises(Exception, match="exceeds 100"):
        otel_events(otlp(*[{"event.name": "unknown"}] * 101))


@pytest.mark.parametrize(
    "credential",
    [
        "OPENAI_API_KEY=canary123456",
        "AWS_SESSION_TOKEN=canary123456",
        "client_secret=canary123456",
        "Bearer canary123456",
        "https://user:canary123456@example.test",
        "-----BEGIN PRIVATE KEY-----\ncanary123456\n-----END PRIVATE KEY-----",
    ],
)
def test_credential_patterns(credential):
    assert "canary123456" not in redact(credential)


def test_event_and_payload_capacities(setup):
    _client, http, record = setup
    endpoint = f"{BASE}/{record['session_id']}"
    event = {
        "event_id": "id",
        "at": AT,
        "kind": "lifecycle",
        "text": "x" * 16000,
        "tool_name": None,
        "status": None,
    }
    batch = [{**event, "event_id": str(index)} for index in range(100)]
    assert http.post(endpoint + "/events", json={"events": batch}).status_code == 200
    before = http.get(endpoint).json
    second = [{**event, "event_id": str(index + 100)} for index in range(100)]
    assert http.post(endpoint + "/events", json={"events": second}).status_code == 409
    assert http.get(endpoint).json == before
    assert (
        http.post(
            endpoint + "/events",
            json={"events": [{**event, "event_id": "oversized", "text": "x" * 16001}]},
        ).status_code
        == 400
    )
