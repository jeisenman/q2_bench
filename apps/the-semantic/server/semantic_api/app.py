"""Loopback HTTP adapter for the shared research protocol."""

import logging
import os
import threading
from pathlib import Path
from typing import Any

from flask import Flask, g, jsonify, request, send_file
from werkzeug.exceptions import HTTPException

from . import validation as valid
from .chat_model import Runner
from .chats import ChatStore, _key
from .documents import DocumentStore
from .gherkin import gherkin_blueprint
from .proposals import ProposalStore
from .session_events import otel_events
from .sessions import SessionStore
from .store import Store
from .transcripts import TranscriptStore


def create_app(
    client: Any = None,
    tracking_uri: str | None = None,
    experiment_name: str | None = None,
    chat_runner: Runner | None = None,
) -> Flask:
    """Build the API, optionally using an isolated MLflow fixture client."""
    os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", "10")
    os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
    os.environ.setdefault("MLFLOW_ENABLE_ASYNC_TRACE_LOGGING", "false")
    tracking_uri = tracking_uri or os.getenv(
        "MLFLOW_TRACKING_URI", "http://127.0.0.1:5055"
    )
    experiment_name = experiment_name or os.getenv(
        "MLFLOW_EXPERIMENT_NAME", "ra/the-semantic"
    )
    if client is None:
        from mlflow import MlflowClient

        client = MlflowClient(tracking_uri=tracking_uri)
    store = Store(client, experiment_name)
    sessions = SessionStore(store)
    proposals = ProposalStore(store)
    documents = DocumentStore(store)
    chats = ChatStore(store, chat_runner)
    transcripts = TranscriptStore(store)
    app = Flask(__name__)
    app.register_blueprint(gherkin_blueprint())
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
    lock = threading.RLock()

    @app.before_request
    def guard() -> None:
        if request.host.split(":")[0] not in ("localhost", "127.0.0.1"):
            raise valid.APIError(
                "invalid_host", "Only loopback hosts are supported.", 403
            )
        g.storage_locked = request.endpoint != "chat_activity"
        if g.storage_locked:
            lock.acquire()

    @app.teardown_request
    def release(error: BaseException | None) -> None:
        if getattr(g, "storage_locked", False):
            g.storage_locked = False
            lock.release()

    @app.errorhandler(Exception)
    def error_response(error: Exception) -> tuple:
        if isinstance(error, valid.APIError):
            return jsonify(
                error={"code": error.code, "message": error.message}
            ), error.status
        if isinstance(error, HTTPException):
            return jsonify(
                error={"code": "invalid_request", "message": error.name}
            ), error.code
        return jsonify(
            error={
                "code": "storage_failure",
                "message": "MLflow operation failed; evidence may be incomplete. Check service availability and retry the same request.",
            }
        ), 502

    @app.get("/health")
    def health() -> dict:
        client.get_experiment(store.experiment_id)
        return {
            "status": "ok",
            "tracking_uri": tracking_uri,
            "experiment_name": experiment_name,
            "experiment_id": str(store.experiment_id),
            "project_root": str(Path(__file__).resolve().parents[2]),
            "capabilities": [
                "research",
                "sessions",
                "proposals",
                "documents",
                "chats",
                "transcripts",
            ],
        }

    @app.route("/api/research/v1/transcripts", methods=["GET", "POST"])
    def transcript_catalog() -> Any:
        """Import explicit historical evidence or read its immutable catalog."""
        if request.method == "POST":
            record, created = transcripts.save(request.get_json())
            return (
                jsonify(record),
                201 if created else 200,
                {} if created else {"Idempotent-Replayed": "true"},
            )
        if set(request.args) - {"order"} or len(request.args.getlist("order")) > 1:
            raise valid.APIError("invalid_query", "Specify one optional order.")
        order = request.args.get("order", "newest")
        if order not in ("newest", "oldest"):
            raise valid.APIError("invalid_order", "Order must be newest or oldest.")
        return {"transcripts": transcripts.list(order)}

    @app.get("/api/research/v1/transcripts/<transcript_id>")
    def transcript_get(transcript_id: str) -> dict:
        """Read captured historical content without invoking a model or tool."""
        if request.args:
            raise valid.APIError("invalid_query", "Transcript reads accept no query.")
        return transcripts.get(transcript_id)

    @app.route("/api/research/v1/chats", methods=["GET", "POST"])
    def chat_catalog() -> Any:
        """Create a chat or list its persisted summaries."""
        if request.method == "POST":
            record, created = chats.create(request.get_json())
            return (
                jsonify(record),
                201 if created else 200,
                ({} if created else {"Idempotent-Replayed": "true"}),
            )
        if set(request.args) - {"order"} or len(request.args.getlist("order")) > 1:
            raise valid.APIError("invalid_query", "Specify one optional order.")
        order = request.args.get("order", "newest")
        if order not in ("newest", "oldest"):
            raise valid.APIError("invalid_order", "Order must be newest or oldest.")
        return {"chats": chats.list(order)}

    @app.get("/api/research/v1/chats/<chat_id>")
    def chat_get(chat_id: str) -> dict:
        """Read one chat without starting a model call."""
        return chats.get(chat_id)

    @app.get("/api/research/v1/chats/<chat_id>/activity")
    def chat_activity(chat_id: str) -> dict:
        """Poll bounded operation metadata without MLflow or the storage lock."""
        valid.identifier(chat_id)
        if set(request.args) != {"key"} or len(request.args.getlist("key")) != 1:
            raise valid.APIError("invalid_query", "Specify one activity UUID key.")
        return chats.activity.get(chat_id, _key(request.args["key"]))

    @app.post("/api/research/v1/chats/<chat_id>/messages")
    def chat_message(chat_id: str) -> Any:
        """Submit one explicit bounded Codex turn, with exact replay safety."""
        record, created = chats.send(chat_id, request.get_json())
        return (
            jsonify(record),
            201 if created else 200,
            ({} if created else {"Idempotent-Replayed": "true"}),
        )

    @app.post("/api/research/v1/proposals/prepare")
    def proposal_prepare() -> Any:
        """Prepare and persist an unaccepted draft attachment."""
        record, created = proposals.save(request.get_json())
        return (
            jsonify(record),
            201 if created else 200,
            ({} if created else {"Idempotent-Replayed": "true"}),
        )

    @app.route("/api/research/v1/documents", methods=["GET", "POST"])
    def document() -> Any:
        """Read or save one versioned local document without starting research."""
        if request.method == "POST":
            record, created = documents.save(request.get_json())
            return (
                jsonify(record),
                201 if created else 200,
                ({} if created else {"Idempotent-Replayed": "true"}),
            )
        if set(request.args) != {"kind", "id"} or any(
            len(request.args.getlist(key)) != 1 for key in request.args
        ):
            raise valid.APIError(
                "invalid_query", "Specify one kind and one document ID."
            )
        return documents.get(request.args["kind"], request.args["id"])

    @app.get("/api/research/v1/documents/history")
    def document_history() -> dict:
        """Read at most 100 original and saved document versions."""
        if set(request.args) != {"kind", "id"} or any(
            len(request.args.getlist(key)) != 1 for key in request.args
        ):
            raise valid.APIError(
                "invalid_query", "Specify one kind and one document ID."
            )
        return documents.history(request.args["kind"], request.args["id"])

    @app.route("/api/research/v1/proposals", methods=["GET", "POST"])
    def proposal_catalog() -> Any:
        """Save an unaccepted draft or read the bounded proposal catalog."""
        if request.method == "POST":
            record, created = proposals.save(request.get_json())
            return (
                jsonify(record),
                201 if created else 200,
                {} if created else {"Idempotent-Replayed": "true"},
            )
        order = request.args.get("order", "newest")
        if order not in ("newest", "oldest"):
            raise valid.APIError("invalid_order", "Order must be newest or oldest.")
        return {"proposals": proposals.list(order)}

    @app.get("/api/research/v1/proposals/<proposal_id>")
    def proposal_get(proposal_id: str) -> dict:
        """Read a proposal without starting or accepting research."""
        return proposals.get(proposal_id)

    @app.route("/api/research/v1/sessions", methods=["GET", "POST"])
    def session_catalog() -> Any:
        if request.method == "POST":
            return jsonify(sessions.create(request.get_json())), 201
        order = request.args.get("order", "newest")
        if order not in ("newest", "oldest"):
            raise valid.APIError("invalid_order", "Order must be newest or oldest.")
        return {"sessions": sessions.list(order)}

    @app.get("/api/research/v1/sessions/<session_id>")
    def session_get(session_id: str) -> dict:
        return sessions.get(session_id)

    @app.post("/api/research/v1/sessions/<session_id>/events")
    def session_events(session_id: str) -> dict:
        record, added = sessions.launcher_events(session_id, request.get_json())
        return {"accepted": added, "ignored": 0, "event_count": record["event_count"]}

    @app.post("/api/research/v1/sessions/<session_id>/otel")
    def session_otel(session_id: str) -> dict:
        events, ignored = otel_events(request.get_json())
        record, added = sessions.append(session_id, events)
        return {
            "accepted": added,
            "ignored": ignored,
            "event_count": record["event_count"],
        }

    @app.post("/api/research/v1/sessions/<session_id>/close")
    def session_close(session_id: str) -> dict:
        return sessions.close(session_id, request.get_json())

    @app.route("/api/research/v1/agents", methods=["GET", "POST"])
    def agents() -> dict:
        return (
            store.put_agent(valid.agent(request.get_json()))
            if request.method == "POST"
            else {"agents": store.agents()}
        )

    @app.get("/api/research/v1/agents/<agent_id>")
    def agent(agent_id: str) -> dict:
        return store.agent(
            valid.identifier(agent_id),
            valid.identifier(request.args.get("version", "1")),
        )

    @app.route("/api/research/v1/research", methods=["GET", "POST"])
    def research() -> dict:
        if request.method == "POST":
            record, created = store.create(valid.spec(request.get_json()))
            return (
                jsonify(record),
                201 if created else 200,
                {} if created else {"Idempotent-Replayed": "true"},
            )
        order = request.args.get("order", "newest")
        if order not in ("newest", "oldest"):
            raise valid.APIError("invalid_order", "Order must be newest or oldest.")
        return {"research": store.records(order)}

    @app.get("/api/research/v1/research/<research_id>")
    def get(research_id: str) -> dict:
        return store.get(valid.identifier(research_id))

    @app.post("/api/research/v1/research/<research_id>/complete")
    def complete(research_id: str) -> dict:
        return store.complete(
            valid.identifier(research_id), valid.completion(request.get_json())
        )

    @app.get("/api/research/v1/page-plugins")
    def plugins() -> dict:
        return {
            "plugins": [
                {
                    "id": "run-summary",
                    "version": "1",
                    "name": "Run Summary",
                    "entry_path": "/plugins/run-summary/index.html",
                    "capabilities": ["research.read"],
                }
            ]
        }

    @app.get("/plugins/run-summary/<filename>")
    def plugin_asset(filename: str) -> Any:
        if filename not in ("index.html", "page.js"):
            raise valid.APIError("not_found", "Plugin asset was not found.", 404)
        response = send_file(
            Path(__file__).resolve().parents[2] / "plugins" / "run-summary" / filename
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; connect-src 'none'; frame-ancestors 'self' file: http://127.0.0.1:4175"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    return app


def main() -> None:
    """Serve one local API process without payload or request logging."""
    logging.getLogger("werkzeug").disabled = True
    port = int(os.getenv("SEMANTIC_API_PORT", "5056"))
    if not 1 <= port <= 65535:
        raise ValueError("SEMANTIC_API_PORT must be from 1 through 65535.")
    create_app().run(host="127.0.0.1", port=port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
