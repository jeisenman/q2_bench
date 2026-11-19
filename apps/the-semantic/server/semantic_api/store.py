"""Persist application records exclusively with public MLflow operations."""

import json
from datetime import UTC, datetime
from typing import Any

from .validation import APIError, digest


class Store:
    """One-process serialized MLflow record store, with no extra database."""

    def __init__(self, client: Any, experiment_name: str) -> None:
        self.client = client
        self.flush_trace = lambda: None
        if hasattr(client, "tracking_uri"):
            import mlflow

            mlflow.set_tracking_uri(client.tracking_uri)
            self.flush_trace = mlflow.flush_trace_async_logging
        experiment = client.get_experiment_by_name(experiment_name)
        self.experiment_id = (
            experiment.experiment_id
            if experiment
            else client.create_experiment(experiment_name)
        )

    def runs(self, kind: str, order: str = "newest") -> list:
        """Read a bounded list, failing explicitly if the catalog is too large."""
        runs = self.client.search_runs(
            [self.experiment_id],
            filter_string=f"tags.`semantic.kind` = '{kind}'",
            max_results=101,
            order_by=[
                f"attributes.start_time {'DESC' if order == 'newest' else 'ASC'}"
            ],
        )
        if len(runs) > 100 or getattr(runs, "token", None):
            raise APIError(
                "limit_exceeded", "MVP supports at most 100 records per catalog.", 409
            )
        return list(runs)

    def read(self, run_id: str, filename: str) -> dict:
        """Read JSON evidence using MLflow's artifact API."""
        path = self.client.download_artifacts(run_id, filename)
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)

    def agents(self) -> list[dict]:
        """Read all bounded agent definitions."""
        from .documents import DocumentStore

        records = {}
        documents = DocumentStore(self)
        for run in self.runs("agent"):
            original = self.read(run.info.run_id, "agent.json")
            records[original["mlflow_run_id"]] = original
            for record in documents.agent_versions(run.info.run_id):
                records[record["mlflow_run_id"]] = record
        if len(records) > 100:
            raise APIError(
                "limit_exceeded", "Agent catalog capacity is 100 records.", 409
            )
        return list(records.values())

    def agent(self, agent_id: str, version: str) -> dict:
        """Return an exact immutable definition or a safe 404."""
        for record in self.agents():
            if record["id"] == agent_id and record["version"] == version:
                return record
        raise APIError("agent_not_found", "Agent ID/version was not found.", 404)

    def put_agent(self, definition: dict, publish: bool = True) -> dict:
        """Create or replay an immutable agent definition."""
        agents = self.agents()
        for record in agents:
            if (record["id"], record["version"]) == (
                definition["id"],
                definition["version"],
            ):
                if record["definition_digest"] != digest(definition):
                    raise APIError(
                        "immutable_conflict",
                        "Agent ID/version already has different content.",
                        409,
                    )
                return record
        pending = self.runs("agent_pending")
        run = next(
            (
                item
                for item in pending
                if (
                    item.data.tags.get("semantic.agent_id"),
                    item.data.tags.get("semantic.agent_version"),
                )
                == (definition["id"], definition["version"])
            ),
            None,
        )
        if run and run.data.tags.get("semantic.definition_digest") != digest(
            definition
        ):
            raise APIError(
                "immutable_conflict",
                "Agent ID/version already has different content.",
                409,
            )
        if (
            not run
            and len(
                {record["mlflow_run_id"] for record in agents}
                | {item.info.run_id for item in pending}
            )
            >= 100
        ):
            raise APIError(
                "limit_exceeded", "Agent catalog capacity is 100 records.", 409
            )
        if not run:
            run = self.client.create_run(
                self.experiment_id,
                tags={
                    "semantic.kind": "agent_pending",
                    "semantic.agent_id": definition["id"],
                    "semantic.agent_version": definition["version"],
                    "semantic.definition_digest": digest(definition),
                    "mlflow.runName": definition["id"],
                },
            )
        record = {
            **definition,
            "definition_digest": digest(definition),
            "mlflow_run_id": run.info.run_id,
        }
        if run.data.tags.get("semantic.agent_ready") != "true":
            self.client.log_dict(run.info.run_id, record, "agent.json")
            self.client.set_terminated(run.info.run_id, "FINISHED")
            self.client.set_tag(run.info.run_id, "semantic.agent_ready", "true")
        if publish:
            self.client.set_tag(run.info.run_id, "semantic.kind", "agent")
        return record

    def records(self, order: str = "newest") -> list[dict]:
        """Read research state from persisted MLflow artifacts."""
        from .documents import DocumentStore

        documents = DocumentStore(self)
        return [
            documents.project("research", self.read(run.info.run_id, "record.json"))
            for run in self.runs("research", order)
        ]

    def get(self, research_id: str) -> dict:
        """Find a research root without exposing arbitrary MLflow artifacts."""
        for record in self.records():
            if record["research_id"] == research_id:
                return record
        raise APIError("research_not_found", "Research ID was not found.", 404)

    def create(self, spec: dict) -> tuple[dict, bool]:
        """Create a persisted research/experiment/attempt hierarchy once."""
        roots = self.runs("research")
        for run in roots:
            if run.data.tags.get("semantic.idempotency") == digest(
                spec["idempotency_key"]
            ):
                if run.data.tags.get("semantic.spec_digest") != digest(spec):
                    raise APIError(
                        "idempotency_conflict",
                        "Idempotency key has different research content.",
                        409,
                    )
                return self.read(run.info.run_id, "record.json"), False
        if len(roots) >= 100:
            raise APIError(
                "limit_exceeded", "Research catalog capacity is 100 records.", 409
            )
        if any(record["status"] == "RUNNING" for record in self.records()):
            raise APIError(
                "execution_active", "One research execution is already RUNNING.", 409
            )
        agent = self.agent(spec["agent_id"], spec["agent_version"])
        root = self.client.create_run(
            self.experiment_id,
            tags={
                "semantic.kind": "research",
                "semantic.idempotency": digest(spec["idempotency_key"]),
                "semantic.spec_digest": digest(spec),
                "mlflow.runName": spec["title"],
            },
        ).info.run_id
        experiment = self.client.create_run(
            self.experiment_id,
            tags={"mlflow.parentRunId": root, "semantic.kind": "experiment"},
        ).info.run_id
        attempt = self.client.create_run(
            self.experiment_id,
            tags={"mlflow.parentRunId": experiment, "semantic.kind": "attempt"},
        ).info.run_id
        now = datetime.now(UTC).isoformat()
        record = {
            key: spec[key]
            for key in (
                "title",
                "question",
                "hypothesis",
                "plan",
                "agent_id",
                "agent_version",
                "max_runs",
                "max_seconds",
            )
        }
        record.update(
            research_id=root,
            experiment_id=experiment,
            attempt_id=attempt,
            agent_definition_digest=agent["definition_digest"],
            model=agent["model"],
            page_plugin=agent["page_plugin"],
            created_at=now,
            updated_at=now,
            status="RUNNING",
            output=None,
            metrics={},
            trace_id=None,
            error=None,
        )
        self.client.log_dict(root, spec, "spec.json")
        self.client.log_dict(root, agent, "agent.json")
        self.client.log_dict(
            root, {"plan": spec["plan"], "spec_digest": digest(spec)}, "plan.json"
        )
        self.client.log_dict(root, record, "record.json")
        return record, True

    def complete(self, research_id: str, completion: dict) -> dict:
        """Save evidence before publishing terminal state; replay exact completion."""
        record = self.get(research_id)
        if record["attempt_id"] != completion["attempt_id"]:
            raise APIError(
                "attempt_conflict", "Attempt does not belong to this research.", 409
            )
        run = self.client.get_run(research_id)
        published_digest = run.data.tags.get("semantic.completion_digest")
        if published_digest and published_digest != digest(completion):
            raise APIError(
                "completion_conflict", "Terminal completion has different content.", 409
            )
        if record["status"] != "RUNNING":
            if not published_digest:
                raise APIError(
                    "incomplete_evidence", "Terminal completion digest is missing.", 502
                )
            return record
        attempt = record["attempt_id"]
        self.client.log_dict(attempt, completion, "completion.json")
        self.client.log_dict(
            attempt, {"events": completion["sdk_events"]}, "sdk-events.json"
        )
        for key, value in completion["metrics"].items():
            self.client.log_metric(attempt, key, float(value))
        span = self.client.start_trace(
            "semantic.sdk.execution",
            span_type="CHAIN",
            inputs={"research_id": research_id, "attempt_id": attempt},
            attributes={"semantic.evidence": "SDK metadata; no internal Codex spans"},
            experiment_id=self.experiment_id,
            run_id=attempt,
        )
        trace_id = span.trace_id
        self.client.end_trace(
            trace_id,
            outputs={"status": completion["status"], "output": completion["output"]},
            status="OK" if completion["status"] == "FINISHED" else "ERROR",
        )
        self.flush_trace()
        self.client.get_trace(trace_id)
        updated = {
            **record,
            **{
                key: completion[key] for key in ("status", "output", "metrics", "error")
            },
            "trace_id": trace_id,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        self.client.set_tag(
            research_id, "semantic.completion_digest", digest(completion)
        )
        self.client.log_dict(research_id, updated, "terminal-record.json")
        for run_id in (attempt, record["experiment_id"], research_id):
            self.client.set_terminated(run_id, completion["status"])
        self.client.log_dict(research_id, updated, "record.json")
        return updated
