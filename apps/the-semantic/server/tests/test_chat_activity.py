"""Live activity stays truthful, bounded, and independent of storage writes."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from test_api import Client
from test_chats import BASE, DRAFT, Runner, make_chat, message

from semantic_api.app import create_app
from semantic_api.chat_activity import ActivityRegistry


def test_live_poll_bypasses_blocked_turn_and_never_calls_storage(tmp_path):
    started, release = Event(), Event()

    def runner(_):
        started.set()
        assert release.wait(5)
        return {"message": "Which outcome?", "proposal": None}

    client = Client(tmp_path)
    app = create_app(client, chat_runner=runner)
    chat, _ = make_chat(app.test_client())
    route = f"{BASE}/{chat['chat_id']}"
    value = message()
    with ThreadPoolExecutor(max_workers=2) as pool:
        sent = pool.submit(app.test_client().post, route + "/messages", json=value)
        try:
            assert started.wait(5)
            search = client.search_runs

            def forbidden(*args, **kwargs):
                raise AssertionError("Activity must not read MLflow.")

            client.search_runs = forbidden
            polled = pool.submit(
                app.test_client().get,
                route + "/activity?key=" + value["idempotency_key"],
            ).result(timeout=2)
            assert polled.status_code == 200
            assert polled.json["done"] is False
            events = polled.json["events"]
            assert [event["name"] for event in events] == [
                "agent_get",
                "research_list",
                "proposal_list",
                "codex_complete",
            ]
            assert events[-1]["status"] == "running"
            assert all(type(event["elapsed_ms"]) is int for event in events)
            client.search_runs = search
        finally:
            release.set()
        response = sent.result(timeout=5)
    assert response.status_code == 201
    terminal = (
        app.test_client().get(route + "/activity?key=" + value["idempotency_key"]).json
    )
    assert terminal["done"] is True
    assert terminal["events"] == response.json["messages"][-1]["activity"]
    assert terminal["events"][-1]["name"] == "chat_save"
    assert all(event["elapsed_ms"] >= 0 for event in terminal["events"])


@pytest.mark.parametrize("failure", [False, True])
def test_activity_persists_and_replay_never_calls_provider(tmp_path, failure):
    runner = Runner(DRAFT)

    def fail(value):
        runner.calls.append(value)
        raise RuntimeError("private payload")

    client = Client(tmp_path)
    app = create_app(client, chat_runner=fail if failure else runner)
    http = app.test_client()
    chat, _ = make_chat(http)
    route = f"{BASE}/{chat['chat_id']}"
    value = message()
    sent = http.post(route + "/messages", json=value)
    events = sent.json["messages"][-1]["activity"]
    status = {event["name"]: event["status"] for event in events}
    assert status["codex_complete"] == ("failed" if failure else "completed")
    assert ("proposal_prepare" in status) is not failure
    assert status["chat_save"] == "completed"
    restarted = create_app(client, chat_runner=runner).test_client()
    assert restarted.get(route).json == sent.json
    assert restarted.post(route + "/messages", json=value).json == sent.json
    assert len(runner.calls) == 1
    http.post(route + "/messages", json=message(1))
    assert '"activity"' not in runner.calls[-1]["input"]


@pytest.mark.parametrize(
    "query", ["", "?key=bad", "?extra=1", "?key={key}&key={key}", "?key={key}&x=1"]
)
def test_activity_rejects_malformed_queries_without_storage(tmp_path, query):
    app = create_app(Client(tmp_path))
    response = app.test_client().get(
        BASE + "/chat/activity" + query.format(key=uuid4())
    )
    assert response.status_code == 400


def test_unknown_activity_is_empty_and_registry_is_bounded():
    registry = ActivityRegistry()
    first = str(uuid4())
    registry.start("chat", first).finish()
    for _ in range(256):
        registry.start("chat", str(uuid4())).finish()
    assert len(registry.turns) == 256
    assert registry.get("chat", first) == {"events": [], "done": False}


def test_storage_failure_ends_live_activity_without_provider_retry(tmp_path):
    client, runner = Client(tmp_path), Runner()
    http = create_app(client, chat_runner=runner).test_client()
    chat, _ = make_chat(http)
    route = f"{BASE}/{chat['chat_id']}"
    log = client.log_dict

    def fail(run_id, value, filename):
        if filename == "chat.json":
            raise RuntimeError("private payload")
        log(run_id, value, filename)

    client.log_dict = fail
    value = message()
    assert http.post(route + "/messages", json=value).status_code == 502
    activity = http.get(route + "/activity?key=" + value["idempotency_key"]).json
    assert activity["done"] is True
    assert activity["events"][-1]["status"] == "failed"
    assert activity["events"][-1]["name"] == "chat_save"
    client.log_dict = log
    assert http.post(route + "/messages", json=value).status_code == 200
    assert len(runner.calls) == 1


def test_preserved_request_context_releases_storage_lock_once(tmp_path):
    app = create_app(Client(tmp_path))
    with app.test_client() as http:
        assert http.get(BASE).status_code == 200
    assert app.test_client().get(BASE).status_code == 200
