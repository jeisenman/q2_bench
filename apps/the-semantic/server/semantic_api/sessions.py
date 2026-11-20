"""Persist selected interactive session evidence through public MLflow APIs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .session_events import event, redact
from .store import Store
from .validation import APIError, digest, identifier, shape, string


class SessionStore:
    """MLflow-backed session records, serialized by the shared API request lock."""

    def __init__(self, store: Store) -> None:
        self.store = store
        self.client = store.client

    def list(self, order: str = "newest") -> list[dict]:
        """Return at most 100 persisted session summaries."""
        return [
            {
                key: value
                for key, value in self.store.read(
                    run.info.run_id, "session.json"
                ).items()
                if key != "events"
            }
            for run in self.store.runs("codex_session", order)
        ]

    def get(self, session_id: str) -> dict:
        """Read only an application-owned session artifact."""
        identifier(session_id)
        for summary in self.list():
            if summary["session_id"] == session_id:
                return self.store.read(session_id, "session.json")
        raise APIError("session_not_found", "Session ID was not found.", 404)

    def create(self, value: dict) -> dict:
        """Persist an ACTIVE session before the launcher starts native Codex."""
        shape(value, {"model", "cwd", "codex_home", "codex_binary"})
        identifier(value["model"])
        for key in ("cwd", "codex_home", "codex_binary"):
            string(value[key], 4096)
            if not Path(value[key]).is_absolute() or any(
                ord(char) < 32 for char in value[key]
            ):
                raise APIError(
                    "invalid_path",
                    "Session paths must be absolute and contain no control characters.",
                )
        if len(self.list()) >= 100:
            raise APIError(
                "limit_exceeded", "Session catalog capacity is 100 records.", 409
            )
        run = self.client.create_run(
            self.store.experiment_id,
            tags={
                "semantic.kind": "codex_session",
                "mlflow.runName": "Interactive Codex session",
            },
        )
        now = datetime.now(UTC).isoformat()
        record = {key: redact(item) for key, item in value.items()}
        record.update(
            session_id=run.info.run_id,
            title="Codex research session",
            created_at=now,
            updated_at=now,
            status="ACTIVE",
            exit_code=None,
            event_count=0,
            message_count=0,
            trace_id=None,
            error=None,
            events=[],
        )
        self.client.log_dict(run.info.run_id, record, "session.json")
        return record

    def append(self, session_id: str, events: list[dict]) -> tuple[dict, int]:
        """Append deduplicated redacted events atomically at the artifact boundary."""
        record = self.get(session_id)
        if record["status"] != "ACTIVE":
            raise APIError("session_closed", "Session is already terminal.", 409)
        known = {item["event_id"]: item for item in record["events"]}
        added = 0
        for item in events:
            if item["event_id"] in known:
                if known[item["event_id"]] != item:
                    raise APIError(
                        "event_conflict", "Event ID already has different content.", 409
                    )
                continue
            known[item["event_id"]] = item
            added += 1
        if len(known) > 1000:
            raise APIError("limit_exceeded", "Session event capacity is 1000.", 409)
        updated = {**record, "events": list(known.values())}
        updated["event_count"] = len(known)
        updated["message_count"] = sum(
            item["kind"] in ("user_message", "assistant_message")
            for item in known.values()
        )
        if added:
            updated["updated_at"] = datetime.now(UTC).isoformat()
        for item in known.values():
            if item["kind"] == "user_message" and item["text"]:
                updated["title"] = item["text"][:100]
                break
        if len(json.dumps(updated, ensure_ascii=False).encode()) > 2 * 1024 * 1024:
            raise APIError("limit_exceeded", "Session evidence capacity is 2 MB.", 409)
        if added:
            self.client.log_dict(session_id, updated, "session.json")
        return updated, added

    def launcher_events(self, session_id: str, value: dict) -> tuple[dict, int]:
        """Accept only bounded launcher lifecycle metadata."""
        shape(value, {"events"})
        if not isinstance(value["events"], list) or len(value["events"]) > 100:
            raise APIError(
                "invalid_events", "Launcher batches support at most 100 events."
            )
        return self.append(
            session_id, [event(item, trusted=True) for item in value["events"]]
        )

    def close(self, session_id: str, value: dict) -> dict:
        """Persist a native summary trace and exact terminal result idempotently."""
        shape(value, {"status", "exit_code", "error"})
        if not isinstance(value["status"], str) or value["status"] not in {
            "CLOSED",
            "INTERRUPTED",
            "FAILED",
        }:
            raise APIError(
                "invalid_status",
                "Session close requires CLOSED, INTERRUPTED or FAILED.",
            )
        code = value["exit_code"]
        if code is not None and (
            type(code) is not int or not -2147483648 <= code <= 2147483647
        ):
            raise APIError(
                "invalid_exit_code",
                "Exit code must be a signed 32-bit integer or null.",
            )
        value = {
            **value,
            "error": None
            if value["error"] is None
            else redact(string(value["error"], 2000)),
        }
        record = self.get(session_id)
        run = self.client.get_run(session_id)
        pinned = run.data.tags.get("semantic.close_digest")
        if pinned and pinned != digest(value):
            raise APIError(
                "session_conflict",
                "Terminal session result has different content.",
                409,
            )
        if record["status"] != "ACTIVE":
            if not pinned:
                raise APIError(
                    "incomplete_evidence",
                    "Terminal session result digest is missing.",
                    502,
                )
            return record
        self.client.log_dict(session_id, value, "close.json")
        span = self.client.start_trace(
            "semantic.codex.session",
            span_type="CHAIN",
            inputs={"session_id": session_id, "model": record["model"]},
            attributes={
                "semantic.evidence": "Session lifecycle and selected Codex OTel log metadata; no hidden reasoning"
            },
            experiment_id=self.store.experiment_id,
            run_id=session_id,
            start_time_ns=int(
                datetime.fromisoformat(record["created_at"]).timestamp() * 1e9
            ),
        )
        self.client.end_trace(
            span.trace_id,
            outputs={
                "status": value["status"],
                "event_count": record["event_count"],
                "message_count": record["message_count"],
            },
            status="OK" if value["status"] == "CLOSED" else "ERROR",
        )
        self.store.flush_trace()
        self.client.get_trace(span.trace_id)
        updated = {
            **record,
            **value,
            "updated_at": datetime.now(UTC).isoformat(),
            "trace_id": span.trace_id,
        }
        self.client.set_tag(session_id, "semantic.close_digest", digest(value))
        self.client.log_dict(session_id, updated, "session-terminal.json")
        self.client.set_terminated(
            session_id,
            "FINISHED"
            if value["status"] == "CLOSED"
            else "KILLED"
            if value["status"] == "INTERRUPTED"
            else "FAILED",
        )
        self.client.log_dict(session_id, updated, "session.json")
        return updated
