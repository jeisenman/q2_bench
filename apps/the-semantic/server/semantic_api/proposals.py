"""Save unaccepted research proposals without allocating experiment attempts."""

from datetime import UTC, datetime
from typing import Any

from .store import Store
from .validation import APIError, digest, identifier, shape, string


def proposal_spec(value: dict) -> dict:
    """Validate a bounded draft; execution fields are deliberately unsupported."""
    shape(value, {"title", "question", "hypothesis", "plan", "idempotency_key"})
    for field in ("question", "hypothesis", "plan"):
        string(value[field], 16000)
    string(value["title"], 1000)
    string(value["idempotency_key"], 128)
    return value


class ProposalStore:
    """Persist immutable drafts via public MLflow APIs under a separate kind.

    The API serializes operations. Pending writes are hidden from catalog reads;
    an identical save resumes publication after an interrupted artifact write.
    A native FINISHED run means storage completed, not research was conducted.
    """

    def __init__(self, store: Store) -> None:
        self.store = store
        self.client = store.client

    def list(self, order: str = "newest") -> list[dict]:
        """Read at most 100 published proposal artifacts in the requested order."""
        from .documents import DocumentStore

        documents = DocumentStore(self.store)
        return [
            documents.project(
                "proposal", self.store.read(run.info.run_id, "proposal.json")
            )
            for run in self.store.runs("proposal", order)
        ]

    def get(self, proposal_id: str) -> dict:
        """Read an application-owned proposal or raise an explicit safe 404."""
        identifier(proposal_id)
        for record in self.list():
            if record["proposal_id"] == proposal_id:
                return record
        raise APIError("proposal_not_found", "Proposal ID was not found.", 404)

    def prepare(self, value: dict) -> tuple[dict, bool]:
        """Prepare a persisted DRAFT attachment without accepting or executing it."""
        return self.save(value)

    def save(self, value: dict) -> tuple[dict, bool]:
        """Save once per key, reject conflicting replays, and recover pending saves."""
        spec = proposal_spec(value)
        runs = self.store.runs("proposal") + self.store.runs("proposal_pending")
        key_digest, spec_digest = digest(spec["idempotency_key"]), digest(spec)
        for run in runs:
            tags = run.data.tags
            if tags.get("semantic.idempotency") != key_digest:
                continue
            if tags.get("semantic.spec_digest") != spec_digest:
                raise APIError(
                    "idempotency_conflict",
                    "Idempotency key has different proposal content.",
                    409,
                )
            if tags["semantic.kind"] == "proposal":
                return self.store.read(run.info.run_id, "proposal.json"), False
            return self._publish(run, spec), False
        if len(runs) >= 100:
            raise APIError(
                "limit_exceeded", "Proposal catalog capacity is 100 records.", 409
            )
        now = datetime.now(UTC).isoformat()
        run = self.client.create_run(
            self.store.experiment_id,
            tags={
                "semantic.kind": "proposal_pending",
                "semantic.idempotency": key_digest,
                "semantic.spec_digest": spec_digest,
                "semantic.created_at": now,
                "mlflow.runName": spec["title"],
            },
        )
        return self._publish(run, spec), True

    def _publish(self, run: Any, spec: dict) -> dict:
        """Write the full artifact before making it visible to catalog readers."""
        now = run.data.tags["semantic.created_at"]
        record = {key: spec[key] for key in ("title", "question", "hypothesis", "plan")}
        record.update(
            proposal_id=run.info.run_id,
            status="DRAFT",
            created_at=now,
            updated_at=now,
        )
        self.client.log_dict(run.info.run_id, record, "proposal.json")
        self.client.set_terminated(run.info.run_id, "FINISHED")
        self.client.set_tag(run.info.run_id, "semantic.kind", "proposal")
        return record
