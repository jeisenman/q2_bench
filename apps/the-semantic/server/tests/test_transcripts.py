"""Historical evidence remains exact, bounded and separate from model execution."""

import json
from copy import deepcopy
from uuid import uuid4

import pytest
from test_api import Client

from semantic_api.app import create_app

BASE = "/api/research/v1/transcripts"
TIME = "2026-11-18T19:02:57.143Z"


def spec():
    return {
        "proposal_id": None,
        "idempotency_key": str(uuid4()),
        "transcript": {
            "source": "Native Codex rollout JSONL",
            "thread_id": "thread-1",
            "title": "Captured conversation",
            "description": "Public historical evidence.",
            "redactions": {},
            "items": [
                {
                    "timestamp": TIME,
                    "type": "message",
                    "role": "user",
                    "phase": None,
                    "content": [{"type": "input_text", "text": "Question"}],
                },
                {
                    "timestamp": TIME,
                    "type": "message",
                    "role": "assistant",
                    "phase": "commentary",
                    "content": [{"type": "output_text", "text": "Checking evidence."}],
                },
                {
                    "timestamp": TIME,
                    "type": "tool_call",
                    "call_id": "call-1",
                    "name": "read",
                    "arguments": '{"inert":"$(do-not-execute)"}',
                    "status": "completed",
                },
                {
                    "timestamp": TIME,
                    "type": "tool_output",
                    "call_id": "call-1",
                    "output": [{"type": "input_text", "text": "Evidence"}],
                },
                {
                    "timestamp": TIME,
                    "type": "message",
                    "role": "assistant",
                    "phase": "final_answer",
                    "content": [{"type": "output_text", "text": "Conclusion"}],
                },
            ],
        },
    }


def test_exact_preservation_restart_catalog_replay_and_no_provider(tmp_path):
    client, calls = Client(tmp_path), []
    http = create_app(
        client, chat_runner=lambda value: calls.append(value)
    ).test_client()
    value = spec()
    response = http.post(BASE, json=value)
    assert response.status_code == 201
    record = response.json
    assert record["transcript"] == value["transcript"] and record["proposal_id"] is None
    http = create_app(
        client, chat_runner=lambda value: calls.append(value)
    ).test_client()
    assert http.get(f"{BASE}/{record['transcript_id']}").json == record
    replay = http.post(BASE, json=value)
    assert replay.status_code == 200 and replay.headers["Idempotent-Replayed"] == "true"
    assert replay.json == record
    summary = http.get(BASE).json["transcripts"][0]
    assert (
        summary["message_count"],
        summary["tool_call_count"],
        summary["tool_output_count"],
    ) == (3, 1, 1)
    assert summary["created_at"] == summary["updated_at"] == record["imported_at"]
    assert http.get("/api/research/v1/chats").json == {"chats": []}
    assert http.get("/api/research/v1/research").json == {"research": []}
    changed = deepcopy(value)
    changed["transcript"]["title"] = "Changed"
    assert http.post(BASE, json=changed).status_code == 409
    assert http.get(f"{BASE}/{record['transcript_id']}").json == record
    assert not calls


def test_proposal_link_requires_saved_proposal(tmp_path):
    client = Client(tmp_path)
    http = create_app(client).test_client()
    value = {**spec(), "proposal_id": "missing"}
    assert http.post(BASE, json=value).status_code == 404
    assert not client.runs
    proposal = http.post(
        "/api/research/v1/proposals",
        json={
            "title": "Draft",
            "question": "Q",
            "hypothesis": "H",
            "plan": "P",
            "idempotency_key": str(uuid4()),
        },
    ).json
    value["proposal_id"] = proposal["proposal_id"]
    record = http.post(BASE, json=value).json
    assert record["proposal_id"] == proposal["proposal_id"]
    assert (
        http.get(BASE).json["transcripts"][0]["proposal_id"] == proposal["proposal_id"]
    )


@pytest.mark.parametrize(
    "stage", ["artifact", "terminated", "publication_before", "publication_after"]
)
def test_pending_hidden_and_exact_replay_recovers_failure(tmp_path, stage):
    client = Client(tmp_path)
    http = create_app(client).test_client()
    log, terminate, tag = client.log_dict, client.set_terminated, client.set_tag

    def fail_log(*args):
        if stage == "artifact":
            raise RuntimeError("private-failure")
        return log(*args)

    def fail_terminate(*args):
        if stage == "terminated":
            raise RuntimeError("private-failure")
        return terminate(*args)

    def fail_tag(*args):
        if stage == "publication_before":
            raise RuntimeError("private-failure")
        tag(*args)
        if stage == "publication_after":
            raise RuntimeError("private-failure")

    client.log_dict, client.set_terminated, client.set_tag = (
        fail_log,
        fail_terminate,
        fail_tag,
    )
    value = spec()
    response = http.post(BASE, json=value)
    assert response.status_code == 502 and "private-failure" not in response.text
    expected_count = 1 if stage == "publication_after" else 0
    assert len(http.get(BASE).json["transcripts"]) == expected_count
    if not expected_count:
        assert http.get(BASE + "/run0").status_code == 404
    client.log_dict, client.set_terminated, client.set_tag = log, terminate, tag
    http = create_app(client).test_client()
    result = http.post(BASE, json=value)
    assert (
        result.status_code == 200 and result.json["transcript"] == value["transcript"]
    )
    assert len(client.runs) == 1
    assert len(http.get(BASE).json["transcripts"]) == 1


@pytest.mark.parametrize(
    "change",
    [
        lambda x: x.update(private_reasoning="hidden"),
        lambda x: x.update(redactions={"unknown": "value"}),
        lambda x: x.update(source="unknown"),
        lambda x: x.update(items=[]),
        lambda x: x.update(items=x["items"] * 201),
        lambda x: x["items"][0].update(role="system"),
        lambda x: x["items"][0].update(phase="analysis"),
        lambda x: x["items"][1].update(phase="analysis"),
        lambda x: x["items"][0].update(timestamp="2026-02-30T10:00:00Z"),
        lambda x: x["items"][0].update(timestamp="2026-11-18T10:00:00"),
        lambda x: x["items"][0]["content"][0].update(type="image"),
        lambda x: x["items"][0]["content"][0].update(text="x" * 262145),
        lambda x: x["items"][2].update(type="unknown"),
        lambda x: x["items"][2].update(status="running"),
        lambda x: x["items"][3].update(call_id="orphan"),
        lambda x: x["items"].append(deepcopy(x["items"][2])),
        lambda x: x["items"].append(deepcopy(x["items"][3])),
        lambda x: x["items"].pop(3),
        lambda x: x["items"][3].update(output=[{"type": "image", "text": "unsafe"}]),
        lambda x: x["items"][3].update(output={"raw": "unknown"}),
    ],
)
def test_invalid_source_rejected_before_persistence(tmp_path, change):
    client = Client(tmp_path)
    http = create_app(client).test_client()
    value = spec()
    change(value["transcript"])
    assert http.post(BASE, json=value).status_code == 400
    assert not client.runs


def test_utf8_byte_bound_and_request_fields(tmp_path):
    client = Client(tmp_path)
    http = create_app(client).test_client()
    value = spec()
    value["transcript"]["items"][0]["content"] = [
        {"type": "input_text", "text": "é" * 262144}
    ] * 2
    assert http.post(BASE, json=value).status_code == 413
    response = http.post(
        BASE,
        data=json.dumps(value, ensure_ascii=False),
        content_type="application/json",
    )
    assert response.status_code == 400
    for change in (
        {"idempotency_key": "bad"},
        {"execute": True},
        {"proposal_id": "../bad"},
    ):
        assert http.post(BASE, json={**spec(), **change}).status_code == 400
    assert not client.runs
    for query in ("?order=bad", "?x=1", "?order=newest&order=oldest"):
        assert http.get(BASE + query).status_code == 400
    assert http.get(BASE + "/missing?x=1").status_code == 400
    assert http.get(BASE + "/missing").status_code == 404


def test_import_limit_includes_pending_and_replay_still_works(tmp_path):
    client = Client(tmp_path)
    http = create_app(client).test_client()
    value = spec()
    assert http.post(BASE, json=value).status_code == 201
    for _ in range(99):
        client.create_run("1", tags={"semantic.kind": "transcript_pending"})
    assert http.post(BASE, json=spec()).status_code == 409
    assert http.post(BASE, json=value).status_code == 200


def test_real_mlflow_persistence(tmp_path):
    from mlflow import MlflowClient

    client = MlflowClient(tracking_uri=f"sqlite:///{tmp_path}/transcripts.db")
    client.create_experiment(
        "transcripts", artifact_location=(tmp_path / "artifacts").as_uri()
    )
    http = create_app(client, experiment_name="transcripts").test_client()
    value = spec()
    record = http.post(BASE, json=value).json
    restarted = create_app(client, experiment_name="transcripts").test_client()
    assert restarted.get(f"{BASE}/{record['transcript_id']}").json == record
    assert restarted.post(BASE, json=value).json == record
