"""Draft storage never creates research attempts or depends on model access."""

import pytest
from test_api import Client

from semantic_api.app import create_app
from semantic_api.proposals import ProposalStore
from semantic_api.store import Store

BASE = "/api/research/v1/proposals"
SPEC = {
    "title": "Loan scenario modeling and realized ROE",
    "question": "Do multiple scenarios precede higher full-life realized ROE?",
    "hypothesis": "The adjusted ROE difference is positive.",
    "plan": "Verify data, compare loans within each RM, report uncertainty.",
    "idempotency_key": "loan scenario proposal 1",
}


def test_save_restart_read_and_replay_without_agents_or_research(tmp_path):
    client = Client(tmp_path)
    http = create_app(client).test_client()
    response = http.post(BASE, json=SPEC)
    assert response.status_code == 201
    record = response.json
    assert set(record) == {
        "proposal_id",
        "title",
        "question",
        "hypothesis",
        "plan",
        "status",
        "created_at",
        "updated_at",
    }
    assert record["status"] == "DRAFT"
    assert len(client.runs) == 1
    run = client.runs[record["proposal_id"]]
    assert run.data.tags["semantic.kind"] == "proposal"
    assert run.info.status == "FINISHED"
    http = create_app(client).test_client()
    assert http.get(f"{BASE}/{record['proposal_id']}").json == record
    assert http.get(BASE).json == {"proposals": [record]}
    replay = http.post(BASE, json=SPEC)
    assert replay.status_code == 200
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert replay.json == record and len(client.runs) == 1
    assert http.get("/api/research/v1/research").json == {"research": []}
    assert http.post(BASE, json={**SPEC, "plan": "changed"}).status_code == 409
    assert http.get(BASE + "?order=oldest").status_code == 200
    assert client.last_order == ["attributes.start_time ASC"]


@pytest.mark.parametrize(
    "change",
    [
        {"title": " "},
        {"title": "x" * 1001},
        {"question": ""},
        {"hypothesis": None},
        {"plan": "x" * 16001},
        {"idempotency_key": "x" * 129},
        {"accepted": True},
        {"max_runs": 1},
    ],
)
def test_invalid_proposals_never_allocate_runs(tmp_path, change):
    client = Client(tmp_path)
    http = create_app(client).test_client()
    assert http.post(BASE, json={**SPEC, **change}).status_code == 400
    assert not client.runs


def test_missing_and_invalid_reads(tmp_path):
    http = create_app(Client(tmp_path)).test_client()
    assert http.get(BASE + "/unknown").status_code == 404
    assert http.get(BASE + "?order=invalid").status_code == 400
    assert http.get(BASE + "/bad$id").status_code == 400


@pytest.mark.parametrize("stage", ["artifact", "publication"])
def test_partial_save_is_hidden_and_identical_replay_recovers(tmp_path, stage):
    client = Client(tmp_path)
    http = create_app(client).test_client()
    original_tag = client.set_tag
    if stage == "artifact":
        client.fail = True
    else:

        def fail_tag(*args):
            raise RuntimeError("sensitive-storage-detail")

        client.set_tag = fail_tag
    failed = http.post(BASE, json=SPEC)
    assert failed.status_code == 502
    assert "sensitive" not in failed.text
    assert http.get(BASE).json == {"proposals": []}
    assert len(client.runs) == 1
    assert http.post(BASE, json={**SPEC, "plan": "different"}).status_code == 409
    client.fail = False
    client.set_tag = original_tag
    recovered = http.post(BASE, json=SPEC)
    assert recovered.status_code == 200
    assert recovered.json["status"] == "DRAFT"
    assert len(client.runs) == 1
    assert http.get(BASE).json == {"proposals": [recovered.json]}


def test_real_mlflow_proposal_persists_without_research_hierarchy(tmp_path):
    from mlflow import MlflowClient

    client = MlflowClient(tracking_uri=f"sqlite:///{tmp_path}/proposals.db")
    client.create_experiment(
        "drafts", artifact_location=(tmp_path / "artifacts").as_uri()
    )
    store = Store(client, "drafts")
    record, created = ProposalStore(store).save(SPEC)
    assert created
    restarted = ProposalStore(Store(client, "drafts"))
    assert restarted.get(record["proposal_id"]) == record
    assert restarted.save(SPEC) == (record, False)
    assert len(store.runs("proposal")) == 1
    assert not store.runs("research")
    assert not store.runs("experiment")
    assert not store.runs("attempt")
