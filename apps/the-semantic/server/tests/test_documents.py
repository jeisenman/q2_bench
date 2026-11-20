"""Versioned edits preserve evidence and publish through one MLflow head."""

import copy
import json
from pathlib import Path
from uuid import uuid4

import pytest
from test_api import Client
from test_proposals import SPEC

from semantic_api.app import create_app
from semantic_api.documents import HEAD

BASE = "/api/research/v1/documents"
SME = '["loans","accounts",""]'


@pytest.fixture
def setup(tmp_path):
    client = Client(tmp_path)
    http = create_app(client).test_client()
    examples = Path(__file__).resolve().parents[2] / "examples"
    agent = json.loads((examples / "agent.json").read_text())
    spec = json.loads((examples / "research.json").read_text())
    assert http.post("/api/research/v1/agents", json=agent).status_code == 200
    return client, http, agent, spec


def query(http, kind, document_id, suffix=""):
    return http.get(BASE + suffix, query_string={"kind": kind, "id": document_id})


def request_for(document, **changes):
    return {
        "kind": document["kind"],
        "id": document["id"],
        "base_version": document["version"],
        "content": {**document["content"], **changes},
        "idempotency_key": str(uuid4()),
    }


def proposal(http):
    record = http.post("/api/research/v1/proposals", json=SPEC).json
    return query(http, "proposal", record["proposal_id"]).json


def test_proposal_versions_conflicts_replays_and_restart(tmp_path):
    client = Client(tmp_path)
    http = create_app(client).test_client()
    original = proposal(http)
    assert original["version"] == 0 and original["updated_at"] is None
    first = request_for(original, title="Edited title")
    response = http.post(BASE, json=first)
    assert response.status_code == 201
    saved = response.json
    assert saved["version"] == 1 and saved["updated_at"].endswith("+00:00")
    assert (
        http.post(BASE, json={**first, "idempotency_key": str(uuid4())}).status_code
        == 409
    )
    assert (
        http.post(BASE, json={**first, "content": original["content"]}).status_code
        == 409
    )
    second = http.post(BASE, json=request_for(saved, plan="Revised plan")).json
    http = create_app(client).test_client()
    assert query(http, "proposal", original["id"]).json == second
    assert query(http, "proposal", original["id"], "/history").json == {
        "versions": [original, saved, second]
    }
    replay = http.post(BASE, json=first)
    assert replay.status_code == 200 and replay.json == saved
    assert replay.headers["Idempotent-Replayed"] == "true"
    canonical = http.get("/api/research/v1/proposals/" + original["id"]).json
    assert canonical["title"] == "Edited title" and canonical["plan"] == "Revised plan"
    assert client.artifacts[original["id"], "proposal.json"]["title"] == SPEC["title"]


def test_terminal_research_projects_edits_and_preserves_execution_evidence(setup):
    client, http, _agent, spec = setup
    record = http.post("/api/research/v1/research", json=spec).json
    original = query(http, "research", record["research_id"]).json
    assert (
        http.post(BASE, json=request_for(original, title="Premature")).status_code
        == 409
    )
    body = {
        "attempt_id": record["attempt_id"],
        "status": "FINISHED",
        "output": "Original answer",
        "metrics": {"tokens": 3},
        "sdk_events": [],
        "error": None,
    }
    http.post(f"/api/research/v1/research/{record['research_id']}/complete", json=body)
    original = query(http, "research", record["research_id"]).json
    before = copy.deepcopy(client.artifacts)
    edited = http.post(
        BASE,
        json=request_for(original, output="Corrected answer", question="New question"),
    )
    assert edited.status_code == 201
    canonical = http.get("/api/research/v1/research/" + record["research_id"]).json
    assert (
        canonical["output"] == "Corrected answer"
        and canonical["question"] == "New question"
    )
    for field in (
        "agent_id",
        "agent_version",
        "agent_definition_digest",
        "attempt_id",
        "experiment_id",
        "metrics",
        "trace_id",
    ):
        assert canonical[field] == before[record["research_id"], "record.json"][field]
    for key, value in before.items():
        assert client.artifacts[key] == value
    assert (
        query(http, "research", record["research_id"], "/history").json["versions"][0]
        == original
    )


def test_agent_edit_adds_immutable_version_and_resolves_latest_from_new_run(setup):
    client, http, agent, _spec = setup
    original_agent = http.get("/api/research/v1/agents").json["agents"][0]
    original = query(http, "agent", original_agent["mlflow_run_id"]).json
    assert (
        http.post(BASE, json=request_for(original, name="Changed")).status_code == 409
    )
    assert (
        http.post(BASE, json=request_for(original, id="other", version="2")).status_code
        == 409
    )
    edited = http.post(BASE, json=request_for(original, name="Changed", version="2"))
    assert edited.status_code == 201
    version2 = http.get(f"/api/research/v1/agents/{agent['id']}?version=2").json
    assert version2["name"] == "Changed"
    assert query(http, "agent", version2["mlflow_run_id"]).json == edited.json
    assert (
        http.get(
            f"/api/research/v1/agents/{agent['id']}?version={agent['version']}"
        ).json
        == original_agent
    )
    assert (
        http.post(
            BASE, json=request_for(edited.json, version=agent["version"])
        ).status_code
        == 409
    )
    next_request = request_for(edited.json, version="3", purpose="New purpose")
    next_request["id"] = version2["mlflow_run_id"]
    third = http.post(BASE, json=next_request)
    assert third.status_code == 201 and third.json["id"] == original["id"]
    assert third.json["version"] == 2
    assert client.artifacts[original["id"], "agent.json"] == original_agent


def test_sme_is_a_local_draft_and_get_has_no_side_effects(tmp_path):
    client = Client(tmp_path)
    http = create_app(client).test_client()
    original = query(http, "sme", SME).json
    assert original == {
        "kind": "sme",
        "id": SME,
        "version": 0,
        "updated_at": None,
        "content": {"text": "", "source_commit": None},
    }
    assert not client.runs
    saved = http.post(
        BASE,
        json=request_for(original, text="Reviewed local draft", source_commit="abc123"),
    )
    assert saved.status_code == 201
    assert query(create_app(client).test_client(), "sme", SME).json == saved.json
    assert {run.data.tags["semantic.kind"] for run in client.runs.values()} == {
        "sme_document",
        "document_version",
    }


@pytest.mark.parametrize(
    "kind,stage",
    [
        ("proposal", "snapshot"),
        ("proposal", "head"),
        ("agent", "snapshot"),
        ("agent", "head"),
        ("agent", "agent"),
        ("sme", "snapshot"),
        ("sme", "head"),
    ],
)
def test_failed_saves_stay_hidden_then_identical_replay_recovers(tmp_path, kind, stage):
    client = Client(tmp_path)
    http = create_app(client).test_client()
    if kind == "proposal":
        original = proposal(http)
        body = request_for(original, title="Updated")
    elif kind == "agent":
        from pathlib import Path

        definition = json.loads(
            (Path(__file__).resolve().parents[2] / "examples/agent.json").read_text()
        )
        agent = http.post("/api/research/v1/agents", json=definition).json
        original = query(http, kind, agent["mlflow_run_id"]).json
        body = request_for(original, version="2", name="Updated")
    else:
        original = query(http, kind, SME).json
        body = request_for(original, text="Updated")
    log, tag = client.log_dict, client.set_tag

    def fail_log(run_id, value, filename):
        if filename == ("agent.json" if stage == "agent" else "snapshot.json"):
            raise RuntimeError("PRIVATE storage detail")
        log(run_id, value, filename)

    def fail_tag(run_id, key, value):
        if key == HEAD:
            raise RuntimeError("PRIVATE storage detail")
        tag(run_id, key, value)

    if stage == "head":
        client.set_tag = fail_tag
    else:
        client.log_dict = fail_log
    failure = http.post(BASE, json=body)
    assert failure.status_code == 502 and "PRIVATE" not in failure.text
    assert query(http, kind, original["id"]).json == original
    if kind == "agent":
        assert len(http.get("/api/research/v1/agents").json["agents"]) == 1
    client.log_dict, client.set_tag = log, tag
    replay = create_app(client).test_client().post(BASE, json=body)
    assert replay.status_code == 200 and replay.json["version"] == 1
    assert len(query(http, kind, original["id"], "/history").json["versions"]) == 2


@pytest.mark.parametrize(
    "change",
    [
        {"base_version": True},
        {"base_version": -1},
        {"base_version": 0.5},
        {"kind": "unknown"},
        {"idempotency_key": "unsafe/key"},
        {"extra": True},
        {"content": {"text": "", "source_commit": None}},
        {"content": {"text": "x" * 16001, "source_commit": None}},
        {"content": {"text": "x", "source_commit": "x" * 129}},
        {"id": '["namespace","",""]'},
        {"id": "{}"},
        {"id": "[]"},
        {"id": "x" * 2049},
        {"content": {"text": "x", "source_commit": None, "approved": True}},
    ],
)
def test_save_boundaries_allocate_nothing(tmp_path, change):
    client = Client(tmp_path)
    http = create_app(client).test_client()
    original = query(http, "sme", SME).json
    assert (
        http.post(
            BASE, json={**request_for(original, text="Draft"), **change}
        ).status_code
        == 400
    )
    assert not client.runs


def test_reads_reject_invalid_or_duplicate_queries_and_missing_sources(tmp_path):
    http = create_app(Client(tmp_path)).test_client()
    for suffix in ("", "/history"):
        assert http.get(BASE + suffix).status_code == 400
        assert http.get(BASE + suffix + "?kind=sme&kind=agent&id=x").status_code == 400
        assert query(http, "proposal", "missing", suffix).status_code == 404


def test_history_limit_includes_original_and_replay_survives_full_history(tmp_path):
    client = Client(tmp_path)
    http = create_app(client).test_client()
    current = query(http, "sme", SME).json
    first = None
    for index in range(99):
        body = request_for(current, text=f"Draft {index}")
        first = first or body
        saved = http.post(BASE, json=body)
        assert saved.status_code == 201
        current = saved.json
    assert len(query(http, "sme", SME, "/history").json["versions"]) == 100
    assert (
        http.post(BASE, json=request_for(current, text="Too many")).status_code == 409
    )
    assert http.post(BASE, json=first).status_code == 200


def test_real_mlflow_document_versions_survive_store_recreation(tmp_path):
    from mlflow import MlflowClient

    from semantic_api.documents import DocumentStore
    from semantic_api.proposals import ProposalStore
    from semantic_api.store import Store

    client = MlflowClient(tracking_uri=f"sqlite:///{tmp_path}/documents.db")
    client.create_experiment(
        "documents", artifact_location=(tmp_path / "artifacts").as_uri()
    )
    store = Store(client, "documents")
    record, _ = ProposalStore(store).save(SPEC)
    documents = DocumentStore(store)
    original = documents.get("proposal", record["proposal_id"])
    body = request_for(original, title="Persisted edit")
    saved, created = documents.save(body)
    assert created
    restarted = DocumentStore(Store(client, "documents"))
    assert restarted.get("proposal", record["proposal_id"]) == saved
    assert restarted.history("proposal", record["proposal_id"]) == {
        "versions": [original, saved]
    }
    assert restarted.save(body) == (saved, False)
    definition = json.loads(
        (Path(__file__).resolve().parents[2] / "examples/agent.json").read_text()
    )
    agent = store.put_agent(definition)
    original_agent = documents.get("agent", agent["mlflow_run_id"])
    agent_body = request_for(
        original_agent, version="persisted-2", name="Persisted agent edit"
    )
    saved_agent, _ = documents.save(agent_body)
    recreated = Store(client, "documents")
    assert (
        recreated.agent(definition["id"], "persisted-2")["name"]
        == "Persisted agent edit"
    )
    assert DocumentStore(recreated).get("agent", agent["mlflow_run_id"]) == saved_agent


def test_maximum_sme_text_and_commit_are_accepted(tmp_path):
    http = create_app(Client(tmp_path)).test_client()
    original = query(http, "sme", SME).json
    response = http.post(
        BASE, json=request_for(original, text="x" * 16000, source_commit="a" * 128)
    )
    assert response.status_code == 201
    assert len(response.json["content"]["text"]) == 16000
