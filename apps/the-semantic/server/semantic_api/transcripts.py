"""Immutable historical evidence imported explicitly into public MLflow artifacts."""

from datetime import UTC, datetime
from typing import Any

from .chats import _key
from .proposals import ProposalStore
from .store import Store
from .transcript_validation import transcript
from .validation import APIError, digest, identifier, shape


class TranscriptStore:
    """Publish an immutable source only after all evidence has been persisted.

    A pending run is hidden. An identical UUID replay may finish its publication;
    neither imports nor reads invoke a provider or inject historical context.
    """

    def __init__(self, store: Store) -> None:
        self.store, self.client = store, store.client

    def get(self, transcript_id: str) -> dict:
        """Read one published immutable source, without changing its payload."""
        identifier(transcript_id)
        for run in self.store.runs("transcript"):
            if run.info.run_id == transcript_id:
                return self.store.read(transcript_id, "transcript.json")
        raise APIError("transcript_not_found", "Transcript ID was not found.", 404)

    def list(self, order: str = "newest") -> list[dict]:
        """Read at most 100 published summaries without exposing pending imports."""
        summaries = []
        for run in self.store.runs("transcript", order):
            record = self.store.read(run.info.run_id, "transcript.json")
            source = record["transcript"]
            summaries.append(
                {
                    "transcript_id": record["transcript_id"],
                    "title": source["title"],
                    "source_thread_id": source["thread_id"],
                    "created_at": record["imported_at"],
                    "updated_at": record["imported_at"],
                    "proposal_id": record["proposal_id"],
                    **{
                        f"{kind}_count": sum(
                            item["type"] == kind for item in source["items"]
                        )
                        for kind in ("message", "tool_call", "tool_output")
                    },
                }
            )
        return sorted(
            summaries,
            key=lambda item: (item["created_at"], item["transcript_id"]),
            reverse=order == "newest",
        )

    def save(self, value: dict) -> tuple[dict, bool]:
        """Import once per UUID, rejecting conflicting content and absent proposals."""
        shape(value, {"transcript", "proposal_id", "idempotency_key"})
        transcript(value["transcript"])
        _key(value["idempotency_key"])
        if value["proposal_id"] is not None:
            ProposalStore(self.store).get(identifier(value["proposal_id"]))
        runs = self.store.runs("transcript") + self.store.runs("transcript_pending")
        for run in runs:
            if run.data.tags.get("semantic.idempotency") != digest(
                value["idempotency_key"]
            ):
                continue
            if run.data.tags["semantic.spec_digest"] != digest(value):
                raise APIError(
                    "idempotency_conflict", "Transcript key has different content.", 409
                )
            if run.data.tags["semantic.kind"] == "transcript":
                return self.get(run.info.run_id), False
            return self._publish(run, value), False
        if len(runs) >= 100:
            raise APIError("limit_exceeded", "Transcript capacity is 100 imports.", 409)
        run = self.client.create_run(
            self.store.experiment_id,
            tags={
                "semantic.kind": "transcript_pending",
                "semantic.created_at": datetime.now(UTC).isoformat(),
                "semantic.idempotency": digest(value["idempotency_key"]),
                "semantic.spec_digest": digest(value),
                "mlflow.runName": value["transcript"]["title"],
            },
        )
        return self._publish(run, value), True

    def _publish(self, run: Any, value: dict) -> dict:
        record = {
            "transcript_id": run.info.run_id,
            "imported_at": run.data.tags["semantic.created_at"],
            "proposal_id": value["proposal_id"],
            "transcript": value["transcript"],
        }
        self.client.log_dict(run.info.run_id, record, "transcript.json")
        self.client.set_terminated(run.info.run_id, "FINISHED")
        self.client.set_tag(run.info.run_id, "semantic.kind", "transcript")
        return record
