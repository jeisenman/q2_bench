"""Immutable MLflow document snapshots with one authoritative head pointer."""

from datetime import UTC, datetime
from typing import Any

from . import document_validation as valid
from .validation import APIError, digest

HEAD = "semantic.document_head"


class DocumentStore:
    """Edit local documents without changing their original execution evidence.

    A snapshot and any immutable agent projection complete before one head tag
    publishes them. Failed saves stay hidden and resume with the same UUID.
    The API process lock serializes saves; multiple API writers are unsupported.
    """

    def __init__(self, store: Any) -> None:
        self.store, self.client = store, store.client

    def _sme_anchor(self, document_id: str, create: bool = False) -> str | None:
        for run in self.store.runs("sme_document"):
            if run.data.tags.get("semantic.identity") == digest(document_id):
                return run.info.run_id
        if not create:
            return None
        if len(self.store.runs("sme_document")) >= 100:
            raise APIError("limit_exceeded", "Local SME draft capacity is 100.", 409)
        run = self.client.create_run(
            self.store.experiment_id,
            tags={
                "semantic.kind": "sme_document",
                "semantic.identity": digest(document_id),
            },
        )
        return run.info.run_id

    def _original(self, kind: str, document_id: str) -> tuple[str | None, dict]:
        valid.identity(kind, document_id)
        if kind == "sme":
            anchor = self._sme_anchor(document_id)
            content = {"text": "", "source_commit": None}
        else:
            expected = kind
            run = next(
                (
                    run
                    for run in self.store.runs(expected)
                    if run.info.run_id == document_id
                ),
                None,
            )
            if run is None:
                if kind == "agent":
                    for source in self.store.runs("agent"):
                        versions = self.agent_versions(source.info.run_id)
                        if any(
                            record["mlflow_run_id"] == document_id
                            for record in versions
                        ):
                            return self._original(kind, source.info.run_id)
                raise APIError("document_not_found", "Document ID was not found.", 404)
            anchor = document_id
            filename = {
                "proposal": "proposal.json",
                "research": "record.json",
                "agent": "agent.json",
            }[kind]
            record = self.store.read(anchor, filename)
            fields = valid.AGENT_FIELDS if kind == "agent" else valid.PROSE
            if kind == "research":
                fields = fields | {"output"}
            content = {key: record[key] for key in fields}
        return anchor, {
            "kind": kind,
            "id": document_id,
            "version": 0,
            "content": content,
            "updated_at": None,
        }

    def _chain(self, anchor: str | None) -> list[dict]:
        if anchor is None:
            return []
        head = self.client.get_run(anchor).data.tags.get(HEAD)
        chain, seen = [], set()
        while head:
            if head in seen or len(chain) >= 99:
                raise APIError(
                    "incomplete_evidence",
                    "Document history is invalid or exceeds 100 versions.",
                    502,
                )
            seen.add(head)
            run = self.client.get_run(head)
            if run.data.tags.get("semantic.owner") != anchor:
                raise APIError(
                    "incomplete_evidence", "Document snapshot owner differs.", 502
                )
            snapshot = self.store.read(head, "snapshot.json")
            chain.append(snapshot)
            head = snapshot["previous"]
        for index, snapshot in enumerate(reversed(chain), 1):
            if snapshot["document"]["version"] != index:
                raise APIError(
                    "incomplete_evidence", "Document history is not contiguous.", 502
                )
        return chain

    def get(self, kind: str, document_id: str) -> dict:
        """Return the published head, or the original version zero."""
        anchor, original = self._original(kind, document_id)
        chain = self._chain(anchor)
        return chain[0]["document"] if chain else original

    def history(self, kind: str, document_id: str) -> dict:
        """Return the original and published saves, oldest first, at most 100."""
        anchor, original = self._original(kind, document_id)
        chain = self._chain(anchor)
        if chain:
            original = chain[-1]["original"]
        return {"versions": [original] + [item["document"] for item in reversed(chain)]}

    def project(self, kind: str, record: dict) -> dict:
        """Project edited fields while retaining all pinned execution metadata."""
        anchor = record[f"{kind}_id"]
        chain = self._chain(anchor)
        if not chain:
            return record
        document = chain[0]["document"]
        return {**record, **document["content"], "updated_at": document["updated_at"]}

    def agent_versions(self, anchor: str) -> list[dict]:
        """Expose staged immutable agent versions only through a published head."""
        return [
            snapshot["agent"]
            for snapshot in reversed(self._chain(anchor))
            if snapshot.get("agent")
        ]

    def _attempts(self, anchor: str) -> list:
        runs = self.client.search_runs(
            [self.store.experiment_id],
            filter_string=f"tags.`semantic.kind` = 'document_version' AND tags.`semantic.owner` = '{anchor}'",
            max_results=101,
            order_by=["attributes.start_time ASC"],
        )
        if len(runs) > 100 or getattr(runs, "token", None):
            raise APIError(
                "limit_exceeded", "Document save capacity is 100 attempts.", 409
            )
        return [run for run in runs if run.data.tags.get("semantic.owner") == anchor]

    def save(self, value: Any) -> tuple[dict, bool]:
        """Save one new full version, with optimistic concurrency and UUID replay."""
        value = valid.save(value)
        kind, document_id = value["kind"], value["id"]
        anchor, original = self._original(kind, document_id)
        document_id = original["id"]
        if (
            kind == "research"
            and self.store.read(anchor, "record.json")["status"] == "RUNNING"
        ):
            raise APIError(
                "research_active", "Only terminal research can be edited.", 409
            )
        if anchor is None:
            if value["base_version"] != 0:
                raise APIError(
                    "version_conflict",
                    "A new local draft requires base_version zero.",
                    409,
                )
            anchor = self._sme_anchor(document_id, create=True)
        chain = self._chain(anchor)
        current = chain[0]["document"] if chain else original
        attempts = self._attempts(anchor)
        key, request_digest = digest(value["idempotency_key"]), digest(value)
        attempt = next(
            (
                run
                for run in attempts
                if run.data.tags.get("semantic.idempotency") == key
            ),
            None,
        )
        created = attempt is None
        if attempt:
            if attempt.data.tags.get("semantic.request_digest") != request_digest:
                raise APIError(
                    "idempotency_conflict",
                    "Save UUID has different document content.",
                    409,
                )
            for snapshot in chain:
                if snapshot["save_id"] == attempt.info.run_id:
                    return snapshot["document"], False
        if current["version"] != value["base_version"]:
            raise APIError(
                "version_conflict",
                "Document changed. Read its latest version before saving.",
                409,
            )
        if current["version"] >= 99 or (not attempt and len(attempts) >= 100):
            raise APIError(
                "limit_exceeded", "Document history supports at most 100 versions.", 409
            )
        if kind == "agent":
            if value["content"]["id"] != original["content"]["id"]:
                raise APIError("immutable_conflict", "Agent ID cannot change.", 409)
            if value["content"]["version"] == current["content"]["version"]:
                raise APIError(
                    "immutable_conflict",
                    "Agent edits require a new agent version.",
                    409,
                )
            if any(
                (record["id"], record["version"])
                == (value["content"]["id"], value["content"]["version"])
                for record in self.store.agents()
            ):
                raise APIError(
                    "immutable_conflict",
                    "Agent edits require an unused agent version.",
                    409,
                )
        if not attempt:
            attempt = self.client.create_run(
                self.store.experiment_id,
                tags={
                    "semantic.kind": "document_version",
                    "semantic.owner": anchor,
                    "semantic.idempotency": key,
                    "semantic.request_digest": request_digest,
                    "semantic.created_at": datetime.now(UTC).isoformat(),
                },
            )
        envelope = {
            "kind": kind,
            "id": document_id,
            "version": current["version"] + 1,
            "content": value["content"],
            "updated_at": attempt.data.tags["semantic.created_at"],
        }
        agent = (
            self.store.put_agent(value["content"], publish=False)
            if kind == "agent"
            else None
        )
        snapshot = {
            "document": envelope,
            "original": chain[-1]["original"] if chain else original,
            "previous": self.client.get_run(anchor).data.tags.get(HEAD),
            "save_id": attempt.info.run_id,
            "agent": agent,
        }
        if attempt.data.tags.get("semantic.snapshot_ready") != "true":
            self.client.log_dict(attempt.info.run_id, snapshot, "snapshot.json")
            self.client.set_terminated(attempt.info.run_id, "FINISHED")
            self.client.set_tag(attempt.info.run_id, "semantic.snapshot_ready", "true")
        else:
            if self.store.read(attempt.info.run_id, "snapshot.json") != snapshot:
                raise APIError(
                    "incomplete_evidence",
                    "Pending save differs from its immutable snapshot.",
                    502,
                )
        self.client.set_tag(anchor, HEAD, attempt.info.run_id)
        return envelope, created
