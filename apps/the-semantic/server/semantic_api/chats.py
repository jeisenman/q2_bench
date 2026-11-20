"""Serialized MLflow research chats with durable no-rerun turn reservations."""

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from .chat_activity import ActivityRegistry, TurnActivity
from .chat_model import FAILURE, Runner, codex_runner, model_request, parse_answer
from .proposals import ProposalStore
from .store import Store
from .validation import APIError, digest, identifier, shape, string

HEAD = "semantic.chat_head"
UNCERTAIN = (
    "This turn was interrupted before its result was published. It will not run "
    "again. Review the saved drafts, then send a new message to continue."
)


def _key(value: object) -> str:
    string(value, 36)
    try:
        if str(UUID(value)) != value.lower():
            raise ValueError
    except (ValueError, AttributeError) as error:
        raise APIError("invalid_key", "Idempotency key must be a UUID.") from error
    return value


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _message(role: str, text: str, proposal_id: str | None = None) -> dict:
    return {
        "id": str(uuid4()),
        "role": role,
        "text": text,
        "created_at": _now(),
        "proposal_id": proposal_id,
        "tool": {"name": "proposal_prepare", "status": "completed"}
        if proposal_id
        else None,
    }


class ChatStore:
    """Publish full chat snapshots using one head tag after persisted evidence.

    Reservations precede provider submission. A recovered reservation never calls
    the provider. Its saved result is published, or an explicit failed turn is
    appended. This trades automatic recovery for at-most-once paid invocation.
    """

    def __init__(self, store: Store, runner: Runner | None = None) -> None:
        self.store, self.client = store, store.client
        self.runner = runner or codex_runner
        self.activity = ActivityRegistry()

    def create(self, value: dict) -> tuple[dict, bool]:
        """Create or replay an empty chat without a model call."""
        shape(value, {"title", "idempotency_key"})
        string(value["title"], 1000)
        _key(value["idempotency_key"])
        runs = self.store.runs("chat") + self.store.runs("chat_pending")
        for run in runs:
            if run.data.tags.get("semantic.idempotency") != digest(
                value["idempotency_key"]
            ):
                continue
            if run.data.tags["semantic.spec_digest"] != digest(value):
                raise APIError(
                    "idempotency_conflict", "Chat key has different content.", 409
                )
            if run.data.tags["semantic.kind"] == "chat":
                return self.get(run.info.run_id), False
            return self._create_publish(run, value), False
        if len(runs) >= 100:
            raise APIError("limit_exceeded", "Chat capacity is 100 records.", 409)
        run = self.client.create_run(
            self.store.experiment_id,
            tags={
                "semantic.kind": "chat_pending",
                "semantic.created_at": _now(),
                "semantic.idempotency": digest(value["idempotency_key"]),
                "semantic.spec_digest": digest(value),
                "mlflow.runName": value["title"],
            },
        )
        return self._create_publish(run, value), True

    def _create_publish(self, run: object, value: dict) -> dict:
        now = run.data.tags["semantic.created_at"]
        record = {
            "chat_id": run.info.run_id,
            "title": value["title"],
            "created_at": now,
            "updated_at": now,
            "version": 0,
            "messages": [],
        }
        self.client.log_dict(run.info.run_id, record, "chat.json")
        self.client.set_tag(run.info.run_id, HEAD, run.info.run_id)
        self.client.set_tag(run.info.run_id, "semantic.kind", "chat")
        return record

    def _run(self, chat_id: str) -> object:
        identifier(chat_id)
        for run in self.store.runs("chat"):
            if run.info.run_id == chat_id:
                return run
        raise APIError("chat_not_found", "Chat ID was not found.", 404)

    def _turns(self, chat_id: str) -> list:
        return [
            run
            for run in self.store.runs(f"chat_turn.{chat_id}")
            if run.data.tags.get("semantic.chat_id") == chat_id
        ]

    def _snapshot(self, chat_id: str) -> dict:
        return self.store.read(self._run(chat_id).data.tags[HEAD], "chat.json")

    def get(self, chat_id: str) -> dict:
        """Read the current snapshot and close any interrupted reserved turn."""
        record = self._snapshot(chat_id)
        for turn in self._turns(chat_id):
            if turn.data.tags.get("semantic.published") == "true":
                continue
            record = self._recover(chat_id, turn, record)
        return record

    def list(self, order: str = "newest") -> list[dict]:
        """Read at most 100 chat summaries."""
        records = [self.get(run.info.run_id) for run in self.store.runs("chat", order)]
        records.sort(key=lambda record: record["created_at"], reverse=order == "newest")
        return [
            {
                **{
                    key: record[key]
                    for key in ("chat_id", "title", "created_at", "updated_at")
                },
                "message_count": len(record["messages"]),
            }
            for record in records
        ]

    def _publish(self, chat_id: str, turn: object, record: dict) -> dict:
        self.client.set_tag(chat_id, HEAD, turn.info.run_id)
        self.client.set_tag(turn.info.run_id, "semantic.published", "true")
        return record

    def _recover(self, chat_id: str, turn: object, current: dict) -> dict:
        if self._run(chat_id).data.tags[HEAD] == turn.info.run_id:
            self.client.set_tag(turn.info.run_id, "semantic.published", "true")
            return current
        if turn.data.tags.get("semantic.ready") == "true":
            record = self.store.read(turn.info.run_id, "chat.json")
        else:
            record = self.store.read(turn.info.run_id, "reserved.json")
            record["messages"].append(_message("assistant", UNCERTAIN))
            record["updated_at"] = _now()
            self.client.log_dict(turn.info.run_id, record, "chat.json")
            self.client.set_tag(turn.info.run_id, "semantic.ready", "true")
        return self._publish(chat_id, turn, record)

    def send(self, chat_id: str, value: dict) -> tuple[dict, bool]:
        """Reserve one turn, invoke one model call, then persist its final reply."""
        shape(value, {"message", "idempotency_key", "base_version"})
        string(value["message"], 16000)
        _key(value["idempotency_key"])
        if type(value["base_version"]) is not int or value["base_version"] < 0:
            raise APIError(
                "invalid_version", "Base version must be a nonnegative integer."
            )
        self._run(chat_id)
        for turn in self._turns(chat_id):
            if turn.data.tags["semantic.idempotency"] != digest(
                value["idempotency_key"]
            ):
                continue
            if turn.data.tags["semantic.spec_digest"] != digest(value):
                raise APIError(
                    "idempotency_conflict", "Message key has different content.", 409
                )
            self.get(chat_id)
            return self.store.read(turn.info.run_id, "chat.json"), False
        record = self.get(chat_id)
        if record["version"] != value["base_version"]:
            raise APIError(
                "version_conflict", "Reload the chat before sending this message.", 409
            )
        if len(record["messages"]) > 98:
            raise APIError("limit_exceeded", "Chat capacity is 100 messages.", 409)
        activity = self.activity.start(chat_id, value["idempotency_key"])
        try:
            return self._send(chat_id, value, record, activity), True
        finally:
            activity.finish()

    def _send(
        self, chat_id: str, value: dict, record: dict, activity: TurnActivity
    ) -> dict:
        # Fail before reservation when bounded context cannot be loaded.
        user = _message("user", value["message"])
        context = model_request(
            self.store, [*record["messages"], user], activity.operation
        )
        turn = self.client.create_run(
            self.store.experiment_id,
            tags={
                "semantic.kind": f"chat_turn.{chat_id}",
                "semantic.chat_id": chat_id,
                "semantic.idempotency": digest(value["idempotency_key"]),
                "semantic.spec_digest": digest(value),
            },
        )
        record = {
            **record,
            "messages": [*record["messages"], user],
            "version": record["version"] + 1,
            "updated_at": _now(),
        }
        self.client.log_dict(turn.info.run_id, record, "reserved.json")
        # Any interruption after reservation is recovered as a failed turn.
        try:
            with activity.operation("codex_complete"):
                result = parse_answer(json.dumps(self.runner(context)))
        except (APIError, ValueError, TypeError, OSError, RuntimeError):
            result = {"message": FAILURE, "proposal": None}
        proposal_id = None
        if result["proposal"] is not None:
            with activity.operation("proposal_prepare"):
                proposal, _ = ProposalStore(self.store).prepare(
                    {**result["proposal"], "idempotency_key": turn.info.run_id}
                )
                proposal_id = proposal["proposal_id"]
        reply = _message("assistant", result["message"], proposal_id)
        record["messages"].append(reply)
        record["updated_at"] = _now()
        try:
            with activity.operation("chat_save"):
                self.client.log_dict(turn.info.run_id, record, "chat.json")
            # Persist measured completed work, never a predicted completion.
            reply["activity"] = activity.snapshot()["events"]
            self.client.log_dict(turn.info.run_id, record, "chat.json")
            self.client.set_tag(turn.info.run_id, "semantic.ready", "true")
            return self._publish(chat_id, turn, record)
        except Exception:
            activity.complete("chat_save", "failed")
            raise
