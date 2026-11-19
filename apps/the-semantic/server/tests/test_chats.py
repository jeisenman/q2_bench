"""Native-chat fixtures prove persisted drafts and safe at-most-once calls."""

import json
from uuid import uuid4

import pytest
from test_api import Client

from semantic_api.app import create_app
from semantic_api.chat_model import INSTRUCTIONS, model_request
from semantic_api.store import Store

BASE = "/api/research/v1/chats"
DRAFT = {
    "title": "Draft",
    "question": "Question",
    "hypothesis": "Claim",
    "plan": "Unknown data; verify access first.",
}


class Runner:
    def __init__(self, proposal=None):
        self.calls = []
        self.proposal = proposal

    def __call__(self, value):
        self.calls.append(value)
        return {
            "message": "Review this draft." if self.proposal else "Which outcome?",
            "proposal": self.proposal,
        }


def make_chat(http):
    value = {"title": "Loan research", "idempotency_key": str(uuid4())}
    response = http.post(BASE, json=value)
    assert response.status_code == 201
    return response.json, value


def message(base_version=0, text="Study lending"):
    return {
        "message": text,
        "idempotency_key": str(uuid4()),
        "base_version": base_version,
    }


def test_restart_and_exact_replay_never_repeat_provider(tmp_path):
    client, runner = Client(tmp_path), Runner()
    http = create_app(client, chat_runner=runner).test_client()
    chat, create = make_chat(http)
    route = f"{BASE}/{chat['chat_id']}/messages"
    value = message()
    sent = http.post(route, json=value)
    assert sent.status_code == 201
    record = sent.json
    assert record["version"] == 1
    assert [item["role"] for item in record["messages"]] == ["user", "assistant"]
    assert all(
        item["proposal_id"] is None and item["tool"] is None
        for item in record["messages"]
    )
    http = create_app(client, chat_runner=runner).test_client()
    assert http.get(f"{BASE}/{chat['chat_id']}").json == record
    assert http.post(BASE, json=create).status_code == 200
    replay = http.post(route, json=value)
    assert replay.json == record and replay.headers["Idempotent-Replayed"] == "true"
    assert len(runner.calls) == 1
    assert http.get(BASE).json["chats"][0]["message_count"] == 2
    assert http.post(route, json={**value, "message": "changed"}).status_code == 409
    assert http.post(route, json=message()).status_code == 409
    assert http.post(BASE, json={**create, "title": "Changed"}).status_code == 409
    assert http.post(route, json=message(1, "Use realized ROE")).status_code == 201
    history = json.loads(runner.calls[-1]["input"])["history"]
    assert [item["text"] for item in history] == [
        "Study lending",
        "Which outcome?",
        "Use realized ROE",
    ]


@pytest.mark.parametrize("text", ["Study lending", "Prepare a proposal now"])
def test_model_can_prepare_autonomously_or_after_explicit_request(tmp_path, text):
    client, runner = Client(tmp_path), Runner(DRAFT)
    http = create_app(client, chat_runner=runner).test_client()
    chat, _ = make_chat(http)
    route = f"{BASE}/{chat['chat_id']}/messages"
    value = message(text=text)
    result = http.post(route, json=value).json
    reply = result["messages"][-1]
    assert reply["tool"] == {"name": "proposal_prepare", "status": "completed"}
    proposal = http.get(f"/api/research/v1/proposals/{reply['proposal_id']}").json
    assert proposal["status"] == "DRAFT" and proposal["plan"] == DRAFT["plan"]
    assert http.post(route, json=value).json == result
    assert len(runner.calls) == 1
    assert not http.get("/api/research/v1/research").json["research"]


def test_keywords_never_force_attachment(tmp_path):
    runner = Runner()
    http = create_app(Client(tmp_path), chat_runner=runner).test_client()
    chat, _ = make_chat(http)
    reply = http.post(
        f"{BASE}/{chat['chat_id']}/messages", json=message(text="Save a proposal")
    ).json["messages"][-1]
    assert reply["proposal_id"] is None


@pytest.mark.parametrize(
    "result",
    [
        {"message": "Missing proposal"},
        {"message": "", "proposal": None},
        {"message": "x", "proposal": {"title": "Incomplete"}},
        {"message": "x" * 16001, "proposal": None},
        "not json",
    ],
)
def test_malformed_model_result_preserves_user_and_never_saves_draft(tmp_path, result):
    client = Client(tmp_path)
    http = create_app(client, chat_runner=lambda _: result).test_client()
    chat, _ = make_chat(http)
    reply = http.post(f"{BASE}/{chat['chat_id']}/messages", json=message()).json
    assert reply["messages"][0]["text"] == "Study lending"
    assert "failed" in reply["messages"][-1]["text"]
    assert reply["messages"][-1]["proposal_id"] is None
    assert http.get("/api/research/v1/proposals").json == {"proposals": []}


def test_provider_failure_is_safe_and_not_retried(tmp_path):
    calls = []

    def fail(value):
        calls.append(value)
        raise RuntimeError("private-provider-payload")

    client = Client(tmp_path)
    http = create_app(client, chat_runner=fail).test_client()
    chat, _ = make_chat(http)
    route, value = f"{BASE}/{chat['chat_id']}/messages", message()
    reply = http.post(route, json=value)
    assert reply.status_code == 201 and "private" not in reply.text
    assert "failed" in reply.json["messages"][-1]["text"]
    assert http.post(route, json=value).json == reply.json
    assert len(calls) == 1


@pytest.mark.parametrize(
    "stage", ["snapshot", "ready", "head", "published", "proposal"]
)
def test_uncertain_storage_never_reruns_provider(tmp_path, stage):
    client, runner = Client(tmp_path), Runner(DRAFT if stage == "proposal" else None)
    http = create_app(client, chat_runner=runner).test_client()
    chat, _ = make_chat(http)
    log, tag = client.log_dict, client.set_tag

    def fail_log(run_id, value, filename):
        if (stage == "snapshot" and filename == "chat.json") or (
            stage == "proposal" and filename == "proposal.json"
        ):
            raise RuntimeError("private-storage")
        log(run_id, value, filename)

    def fail_tag(run_id, key, value):
        if (
            (stage == "ready" and key == "semantic.ready")
            or (stage == "head" and key == "semantic.chat_head")
            or (stage == "published" and key == "semantic.published")
        ):
            tag(run_id, key, value)
            raise RuntimeError("private-storage")
        tag(run_id, key, value)

    client.log_dict, client.set_tag = fail_log, fail_tag
    route, value = f"{BASE}/{chat['chat_id']}/messages", message()
    failed = http.post(route, json=value)
    assert failed.status_code == 502 and "private" not in failed.text
    client.log_dict, client.set_tag = log, tag
    http = create_app(client, chat_runner=runner).test_client()
    recovered = http.post(route, json=value)
    assert recovered.status_code == 200
    assert recovered.json["messages"][0]["text"] == value["message"]
    assert len(recovered.json["messages"]) == 2 and len(runner.calls) == 1
    assert http.get(f"{BASE}/{chat['chat_id']}").json == recovered.json


@pytest.mark.parametrize(
    "change",
    [
        {"message": ""},
        {"message": "x" * 16001},
        {"base_version": True},
        {"base_version": -1},
        {"base_version": 1.0},
        {"idempotency_key": "not UUID"},
        {"accepted": True},
    ],
)
def test_invalid_messages_never_call_provider(tmp_path, change):
    runner = Runner()
    http = create_app(Client(tmp_path), chat_runner=runner).test_client()
    chat, _ = make_chat(http)
    assert (
        http.post(
            f"{BASE}/{chat['chat_id']}/messages", json={**message(), **change}
        ).status_code
        == 400
    )
    assert not runner.calls


def test_context_exact_agent_and_failed_research_is_not_finding(tmp_path):
    client = Client(tmp_path)
    store = Store(client, "test")
    agent = {
        "id": "hypothesis",
        "version": "1",
        "instructions": "Exact immutable instructions",
    }
    store.agent = lambda _id, _version: agent
    store.records = lambda: [
        {
            "research_id": "failed",
            "title": "Failed",
            "question": "Q",
            "status": "FAILED",
            "output": "Must not be used as finding",
        }
    ]
    context = model_request(store, [{"text": "recent"}])
    assert (
        context["instructions"]
        == INSTRUCTIONS + "\nExact hypothesis/1 instructions:\n" + agent["instructions"]
    )
    saved = json.loads(context["input"])["saved_context"]
    assert saved[0]["output"] is None and saved[0]["finding_available"] is False
    store.records = list
    context = model_request(store, [{"text": "x" * 60000}, {"text": "y" * 60000}])
    assert json.loads(context["input"])["history_truncated"] is True


def test_prepare_http_alias_and_boundaries(tmp_path):
    http = create_app(Client(tmp_path)).test_client()
    spec = {**DRAFT, "idempotency_key": str(uuid4())}
    prepared = http.post("/api/research/v1/proposals/prepare", json=spec)
    assert prepared.status_code == 201 and prepared.json["status"] == "DRAFT"
    assert http.post("/api/research/v1/proposals", json=spec).json == prepared.json
    assert http.get(BASE + "?order=oldest").json == {"chats": []}
    for query in ("?order=bad", "?extra=1", "?order=newest&order=oldest"):
        assert http.get(BASE + query).status_code == 400
    assert http.get(BASE + "/missing").status_code == 404
    assert (
        http.post(BASE, json={"title": "x", "idempotency_key": "invalid"}).status_code
        == 400
    )


def test_chat_message_limit_and_missing_agent_are_explicit(tmp_path):
    runner = Runner()
    client = Client(tmp_path)
    http = create_app(client, chat_runner=runner).test_client()
    chat, _ = make_chat(http)
    chat["messages"] = [
        {
            "id": str(uuid4()),
            "role": "user",
            "text": "Prior",
            "created_at": chat["created_at"],
            "proposal_id": None,
            "tool": None,
        }
    ] * 100
    client.log_dict(chat["chat_id"], chat, "chat.json")
    assert (
        http.post(f"{BASE}/{chat['chat_id']}/messages", json=message()).status_code
        == 409
    )
    assert not runner.calls
    context = model_request(Store(client, "test"), [{"text": "new"}])
    assert json.loads(context["input"])["hypothesis_1"] == "not_found"


def test_real_mlflow_chat_survives_restart_without_repeat_call(tmp_path):
    from mlflow import MlflowClient

    client = MlflowClient(tracking_uri=f"sqlite:///{tmp_path}/chats.db")
    client.create_experiment(
        "chats", artifact_location=(tmp_path / "artifacts").as_uri()
    )
    runner = Runner(DRAFT)
    http = create_app(client, experiment_name="chats", chat_runner=runner).test_client()
    chat, _ = make_chat(http)
    route, value = f"{BASE}/{chat['chat_id']}/messages", message()
    response = http.post(route, json=value)
    assert response.status_code == 201
    restarted = create_app(
        client, experiment_name="chats", chat_runner=runner
    ).test_client()
    assert restarted.get(f"{BASE}/{chat['chat_id']}").json == response.json
    assert restarted.post(route, json=value).json == response.json
    assert len(runner.calls) == 1
