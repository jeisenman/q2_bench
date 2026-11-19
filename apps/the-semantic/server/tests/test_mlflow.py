"""Public MLflow client contract smoke test against an isolated local store."""

import json
from pathlib import Path

from mlflow import MlflowClient

from semantic_api.sessions import SessionStore
from semantic_api.store import Store


def test_public_mlflow_persistence_and_native_trace(tmp_path):
    client = MlflowClient(tracking_uri=f"sqlite:///{tmp_path}/tracking.db")
    experiment = client.create_experiment(
        "isolated", artifact_location=(tmp_path / "artifacts").as_uri()
    )
    assert experiment
    store = Store(client, "isolated")
    examples = Path(__file__).resolve().parents[2] / "examples"
    store.put_agent(json.loads((examples / "agent.json").read_text()))
    record, created = store.create(json.loads((examples / "research.json").read_text()))
    assert created
    done = store.complete(
        record["research_id"],
        {
            "attempt_id": record["attempt_id"],
            "status": "FINISHED",
            "output": "72; 24",
            "metrics": {"input_tokens": 10, "duration_seconds": 0.3},
            "sdk_events": [{"name": "end", "type": "model"}],
            "error": None,
        },
    )
    assert done["trace_id"]
    assert client.get_trace(done["trace_id"]).info.trace_id == done["trace_id"]
    assert Store(client, "isolated").get(record["research_id"]) == done


def test_public_mlflow_session_persistence_and_summary_trace(tmp_path):
    client = MlflowClient(tracking_uri=f"sqlite:///{tmp_path}/sessions.db")
    client.create_experiment(
        "sessions", artifact_location=(tmp_path / "session-artifacts").as_uri()
    )
    sessions = SessionStore(Store(client, "sessions"))
    record = sessions.create(
        {
            "model": "gpt-6.1-sol",
            "cwd": "/tmp/project",
            "codex_home": "/tmp/home",
            "codex_binary": "/tmp/codex",
        }
    )
    assert SessionStore(Store(client, "sessions")).get(record["session_id"]) == record
    done = sessions.close(
        record["session_id"], {"status": "CLOSED", "exit_code": 0, "error": None}
    )
    trace = client.get_trace(done["trace_id"])
    assert trace.data.spans and trace.info.trace_id == done["trace_id"]
    assert SessionStore(Store(client, "sessions")).get(record["session_id"]) == done
