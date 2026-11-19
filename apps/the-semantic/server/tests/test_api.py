"""Protocol checks with a persistent isolated public-client fixture."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from semantic_api.app import create_app


class Client:
    def __init__(self, tmp_path):
        self.path = tmp_path
        self.runs = {}
        self.artifacts = {}
        self.fail = False

    def get_experiment_by_name(self, name):
        return NS(experiment_id="1")

    def get_experiment(self, experiment_id):
        return NS(experiment_id=experiment_id)

    def search_runs(self, experiments, filter_string, max_results, order_by):
        self.last_order = order_by
        kind = filter_string.split("'")[1]
        return [
            r for r in self.runs.values() if r.data.tags.get("semantic.kind") == kind
        ][:max_results]

    def create_run(self, experiment_id, tags):
        run = NS(info=NS(run_id=f"run{len(self.runs)}"), data=NS(tags=tags.copy()))
        self.runs[run.info.run_id] = run
        return run

    def log_dict(self, run_id, value, artifact_file):
        if self.fail:
            raise RuntimeError("sensitive-provider-detail")
        self.artifacts[run_id, artifact_file] = copy.deepcopy(value)

    def download_artifacts(self, run_id, filename):
        path = self.path / f"{run_id}-{filename}"
        path.write_text(json.dumps(self.artifacts[run_id, filename]))
        return str(path)

    def get_run(self, run_id):
        return self.runs[run_id]

    def set_terminated(self, run_id, status):
        self.runs[run_id].info.status = status

    def set_tag(self, run_id, key, value):
        self.runs[run_id].data.tags[key] = value

    def log_metric(self, run_id, key, value):
        pass

    def start_trace(self, *args, **kwargs):
        return NS(trace_id="tr-fixture")

    def end_trace(self, *args, **kwargs):
        pass

    def get_trace(self, trace_id):
        return NS(info=NS(trace_id=trace_id))


@pytest.fixture
def setup(tmp_path):
    client = Client(tmp_path)
    http = create_app(client).test_client()
    examples = Path(__file__).resolve().parents[2] / "examples"
    agent = json.loads((examples / "agent.json").read_text())
    spec = json.loads((examples / "research.json").read_text())
    assert http.post("/api/research/v1/agents", json=agent).status_code == 200
    return client, http, agent, spec


def test_persistence_idempotency_completion(setup):
    client, http, _agent, spec = setup
    response = http.post("/api/research/v1/research", json=spec)
    assert response.status_code == 201
    record = response.json
    http = create_app(client).test_client()
    replay = http.post("/api/research/v1/research", json=spec)
    assert replay.status_code == 200
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert replay.json == record
    assert (
        http.post(
            "/api/research/v1/research", json={**spec, "title": "changed"}
        ).status_code
        == 409
    )
    assert (
        http.post(
            "/api/research/v1/research", json={**spec, "idempotency_key": "other"}
        ).status_code
        == 409
    )
    body = {
        "attempt_id": record["attempt_id"],
        "status": "FINISHED",
        "output": "72; 24",
        "metrics": {"input_tokens": 4},
        "sdk_events": [
            {"name": "span", "trace_id": "t", "span_id": "s", "type": "model"}
        ],
        "error": None,
    }
    route = f"/api/research/v1/research/{record['research_id']}/complete"
    assert http.post(route, json={**body, "attempt_id": "wrong"}).status_code == 409
    done = http.post(route, json=body)
    assert done.status_code == 200
    assert done.json["status"] == "FINISHED" and done.json["trace_id"]
    assert http.post(route, json=body).json == done.json
    assert http.post(route, json={**body, "output": "different"}).status_code == 409
    assert (
        create_app(client)
        .test_client()
        .get(f"/api/research/v1/research/{record['research_id']}")
        .json
        == done.json
    )


def test_boundary_validation_and_immutable_agent(setup):
    client, http, agent, spec = setup
    assert http.post("/api/research/v1/agents", json=agent).status_code == 200
    assert (
        http.post(
            "/api/research/v1/agents", json={**agent, "name": "changed"}
        ).status_code
        == 409
    )
    for update in (
        {"max_runs": 2},
        {"max_runs": True},
        {"max_seconds": 0},
        {"max_seconds": 301},
        {"accepted": False},
        {"agent_id": "../secret"},
    ):
        assert (
            http.post("/api/research/v1/research", json={**spec, **update}).status_code
            == 400
        )
    assert http.get("/api/research/v1/research?order=invalid").status_code == 400
    assert http.get("/api/research/v1/research/unknown").status_code == 404
    assert http.get("/api/research/v1/research?order=oldest").status_code == 200
    assert client.last_order == ["attributes.start_time ASC"]
    assert http.get("/health").json["status"] == "ok"
    assert http.get("/plugins/run-summary/secret").status_code == 404


def test_artifact_failure_never_publishes_finished(setup):
    client, http, _agent, spec = setup
    record = http.post("/api/research/v1/research", json=spec).json
    body = {
        "attempt_id": record["attempt_id"],
        "status": "FINISHED",
        "output": "answer",
        "metrics": {},
        "sdk_events": [],
        "error": None,
    }
    route = f"/api/research/v1/research/{record['research_id']}/complete"
    client.fail = True
    failure = http.post(route, json=body)
    assert failure.status_code == 502
    assert "sensitive-provider-detail" not in failure.text
    assert (
        http.get(f"/api/research/v1/research/{record['research_id']}").json["status"]
        == "RUNNING"
    )
    client.fail = False
    assert (
        http.post(route, json={**body, "metrics": {"tokens": float("nan")}}).status_code
        == 400
    )
    assert (
        http.post(
            route, json={**body, "sdk_events": [{"raw_log": "secret"}]}
        ).status_code
        == 400
    )
    assert (
        http.post(
            route, json={**body, "status": "FAILED", "error": "Provider access denied."}
        ).json["status"]
        == "FAILED"
    )


def test_final_publication_failure_keeps_required_evidence(setup):
    client, http, _agent, spec = setup
    record = http.post("/api/research/v1/research", json=spec).json
    original_log = client.log_dict

    def fail_publication(run_id, value, artifact_file):
        if artifact_file == "record.json":
            raise RuntimeError("publication failed")
        original_log(run_id, value, artifact_file)

    client.log_dict = fail_publication
    body = {
        "attempt_id": record["attempt_id"],
        "status": "FINISHED",
        "output": "answer",
        "metrics": {},
        "sdk_events": [],
        "error": None,
    }
    route = f"/api/research/v1/research/{record['research_id']}/complete"
    assert http.post(route, json=body).status_code == 502
    assert (
        http.get(f"/api/research/v1/research/{record['research_id']}").json["status"]
        == "RUNNING"
    )
    terminal = client.artifacts[record["research_id"], "terminal-record.json"]
    assert terminal["status"] == "FINISHED" and terminal["trace_id"]
    assert client.artifacts[record["attempt_id"], "completion.json"] == body
    client.log_dict = original_log
    assert http.post(route, json={**body, "output": "conflict"}).status_code == 409
    assert http.post(route, json=body).json["status"] == "FINISHED"
