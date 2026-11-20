"""Bounded protocol validation and deterministic digests."""

import hashlib
import json
import math
import re
from typing import Any


class APIError(Exception):
    """A safe error that can be returned through the public HTTP API."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def digest(value: Any) -> str:
    """Return a stable SHA-256 digest of JSON data."""
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def identifier(value: Any) -> str:
    """Validate a safe catalog or MLflow identifier."""
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value
    ):
        raise APIError("invalid_id", "Identifiers must contain 1..128 safe characters.")
    return value


def shape(value: Any, fields: set[str]) -> dict:
    """Require an exact JSON object contract."""
    if not isinstance(value, dict) or set(value) != fields:
        raise APIError("invalid_shape", "JSON object fields do not match the protocol.")
    return value


def string(value: Any, maximum: int = 16000, empty: bool = False) -> str:
    """Require a bounded string."""
    if (
        not isinstance(value, str)
        or len(value) > maximum
        or (not empty and not value.strip())
    ):
        raise APIError(
            "invalid_string",
            f"Expected a string with {'0' if empty else '1'}..{maximum} characters.",
        )
    return value


def agent(value: Any) -> dict:
    """Validate an immutable agent definition."""
    value = shape(
        value,
        {
            "id",
            "version",
            "name",
            "purpose",
            "instructions",
            "model",
            "allowed_tools",
            "page_plugin",
        },
    )
    for field in ("id", "version"):
        identifier(value[field])
    for field in ("name", "purpose", "instructions", "model"):
        string(value[field], 16000 if field == "instructions" else 1000)
    if value["allowed_tools"] != [] or value["page_plugin"] != "run-summary":
        raise APIError(
            "unsupported_agent", "MVP requires empty allowed_tools and run-summary."
        )
    return value


def spec(value: Any) -> dict:
    """Validate the accepted single-attempt research contract."""
    value = shape(
        value,
        {
            "title",
            "question",
            "hypothesis",
            "plan",
            "agent_id",
            "agent_version",
            "accepted",
            "max_runs",
            "max_seconds",
            "idempotency_key",
        },
    )
    for field in ("title", "question", "hypothesis", "plan", "idempotency_key"):
        string(value[field], 128 if field == "idempotency_key" else 16000)
    identifier(value["agent_id"])
    identifier(value["agent_version"])
    if (
        value["accepted"] is not True
        or type(value["max_runs"]) is not int
        or value["max_runs"] != 1
    ):
        raise APIError("unsupported_plan", "Accept the plan and set max_runs to 1.")
    if type(value["max_seconds"]) is not int or not 1 <= value["max_seconds"] <= 300:
        raise APIError(
            "invalid_timeout", "max_seconds must be an integer from 1 through 300."
        )
    return value


def completion(value: Any) -> dict:
    """Validate terminal evidence without retaining arbitrary provider logs."""
    value = shape(
        value, {"attempt_id", "status", "output", "metrics", "sdk_events", "error"}
    )
    identifier(value["attempt_id"])
    if value["status"] not in ("FINISHED", "FAILED", "KILLED"):
        raise APIError("invalid_status", "Completion requires a terminal status.")
    string(value["output"], 200000, empty=True)
    if value["error"] is not None:
        string(value["error"], 2000)
    metrics = value["metrics"]
    if not isinstance(metrics, dict) or len(metrics) > 100:
        raise APIError(
            "invalid_metrics", "Expected at most 100 finite numeric metrics."
        )
    for key, number in metrics.items():
        identifier(key)
        if (
            type(number) not in (int, float)
            or not math.isfinite(number)
            or abs(number) > 1e100
        ):
            raise APIError("invalid_metrics", "Metrics must be bounded finite numbers.")
    events = value["sdk_events"]
    if not isinstance(events, list) or len(events) > 1000:
        raise APIError("invalid_events", "Expected at most 1000 SDK metadata events.")
    for event in events:
        if not isinstance(event, dict) or not set(event).issubset(
            {"name", "event", "trace_id", "span_id", "type"}
        ):
            raise APIError(
                "invalid_events", "SDK events must contain metadata fields only."
            )
        for item in event.values():
            string(item, 256, empty=True)
    if value["status"] == "FINISHED" and (
        not value["output"].strip() or value["error"] is not None
    ):
        raise APIError("invalid_completion", "FINISHED requires output and no error.")
    return value
