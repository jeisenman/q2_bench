"""Check the packaged hypothesis role through persistent public API operations."""

import json
from pathlib import Path

from mlflow import MlflowClient

from semantic_api.app import create_app
from semantic_api.validation import digest


def test_hypothesis_registration_restart_immutability_and_no_research(tmp_path):
    """Register the real definition without accepting or creating research."""
    root = Path(__file__).resolve().parents[2]
    definition = json.loads((root / "agents/hypothesis/agent.json").read_text())
    client = MlflowClient(tracking_uri=f"sqlite:///{tmp_path}/hypothesis.db")
    experiment = client.create_experiment(
        "hypothesis", artifact_location=(tmp_path / "artifacts").as_uri()
    )
    http = create_app(client, experiment_name="hypothesis").test_client()
    response = http.post("/api/research/v1/agents", json=definition)
    assert response.status_code == 200
    record = response.json
    assert record["definition_digest"] == digest(definition)
    assert record["model"] == "gpt-6.1-sol"
    assert record["allowed_tools"] == []

    restarted = create_app(client, experiment_name="hypothesis").test_client()
    assert restarted.post("/api/research/v1/agents", json=definition).json == record
    assert restarted.get("/api/research/v1/agents/hypothesis?version=1").json == record
    assert restarted.get("/api/research/v1/agents").json == {"agents": [record]}
    changed = {**definition, "instructions": "A different instruction contract."}
    conflict = restarted.post("/api/research/v1/agents", json=changed)
    assert conflict.status_code == 409
    assert conflict.json["error"]["code"] == "immutable_conflict"
    assert (
        restarted.get("/api/research/v1/agents/hypothesis?version=2").status_code == 404
    )
    assert restarted.get("/api/research/v1/research").json == {"research": []}
    runs = client.search_runs([experiment])
    assert len(runs) == 1
    assert runs[0].data.tags["semantic.kind"] == "agent"
