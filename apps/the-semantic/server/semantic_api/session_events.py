"""Normalize explicitly selected session evidence and remove credentials."""

import math
import re
from datetime import UTC, datetime
from typing import Any

from .validation import APIError, digest, shape, string

_PATTERNS = [
    (
        r"(?s)-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        "[REDACTED]",
    ),
    (r"\b(?:ghp_|github_pat_|xox[baprs]-)[A-Za-z0-9_-]{8,}", "[REDACTED]"),
    (r"(?i)\bBearer\s+[^\s,;\"']+", "Bearer [REDACTED]"),
    (r"\b(?:sk|sk-proj|sk-ant)-[A-Za-z0-9_-]{8,}", "[REDACTED]"),
    (r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b", "[REDACTED]"),
    (r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", "[REDACTED]"),
    (
        r"(?i)\b(?:[a-z0-9]+[_-])*(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret|authorization|aws_secret_access_key)\b[\"']?\s*[:=]\s*[\"']?[^\s,;\"'}]+",
        "[REDACTED]",
    ),
    (r"(?i)(https?://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@"),
]


def redact(value: str) -> str:
    """Remove common credential forms before any artifact write."""
    for pattern, replacement in _PATTERNS:
        value = re.sub(pattern, replacement, value)
    return value


def timestamp(value: Any) -> str:
    """Validate and normalize a UTC ISO timestamp with bounded years."""
    string(value, 40)
    try:
        parsed = datetime.fromisoformat(value)
        if (
            parsed.tzinfo is None
            or parsed.utcoffset().total_seconds() != 0
            or not 2000 <= parsed.year <= 2100
        ):
            raise ValueError
    except (ValueError, OverflowError, AttributeError) as error:
        raise APIError(
            "invalid_timestamp", "Event time must be UTC ISO from 2000 through 2100."
        ) from error
    return parsed.astimezone(UTC).isoformat()


def event(value: Any, trusted: bool = False) -> dict:
    """Validate one normalized event; launcher input is lifecycle metadata only."""
    value = shape(value, {"event_id", "at", "kind", "text", "tool_name", "status"})
    string(value["event_id"], 256)
    kind = value["kind"]
    if not isinstance(kind, str) or kind not in {
        "user_message",
        "assistant_message",
        "tool",
        "warning",
        "error",
        "lifecycle",
    }:
        raise APIError("invalid_event", "Unsupported session event kind.")
    if trusted and kind not in {"lifecycle", "warning", "error"}:
        raise APIError(
            "invalid_event",
            "Launcher events support lifecycle, warning and error metadata only.",
        )
    result = {
        "event_id": digest(value["event_id"]),
        "at": timestamp(value["at"]),
        "kind": kind,
    }
    for key, maximum in (("text", 16000), ("tool_name", 128), ("status", 128)):
        item = value[key]
        result[key] = (
            None if item is None else redact(string(item, maximum, empty=True))
        )
    if kind == "tool" and result["text"] is not None:
        raise APIError("invalid_event", "Tool payload text is unsupported.")
    return result


def _bounds(value: Any, depth: int = 0) -> None:
    if depth > 12:
        raise APIError("invalid_otel", "OTLP nesting exceeds 12 levels.")
    if isinstance(value, dict):
        if len(value) > 100:
            raise APIError("invalid_otel", "OTLP object has too many members.")
        for key, item in value.items():
            string(key, 256)
            _bounds(item, depth + 1)
    elif isinstance(value, list):
        if len(value) > 1000:
            raise APIError("invalid_otel", "OTLP array exceeds 1000 items.")
        for item in value:
            _bounds(item, depth + 1)
    elif isinstance(value, str):
        string(value, 65536, empty=True)
    elif isinstance(value, float) and not math.isfinite(value):
        raise APIError("invalid_otel", "OTLP numbers must be finite.")
    elif value is not None and type(value) not in (bool, int, float):
        raise APIError("invalid_otel", "Unsupported OTLP value.")


def otel_events(body: Any) -> tuple[list[dict], int]:
    """Decode source-verified Codex log attributes; discard all other payloads."""
    _bounds(body)
    if not isinstance(body, dict) or not isinstance(body.get("resourceLogs"), list):
        raise APIError("invalid_otel", "Expected OTLP JSON resourceLogs.")
    events, ignored, count = [], 0, 0
    try:
        for resource in body["resourceLogs"]:
            for scope in resource.get("scopeLogs", []):
                for record in scope.get("logRecords", []):
                    count += 1
                    if count > 100:
                        raise APIError(
                            "invalid_otel", "OTLP batch exceeds 100 log records."
                        )
                    attrs = {}
                    for attr in record.get("attributes", []):
                        key, value = attr["key"], attr["value"]
                        if key in attrs:
                            raise APIError("invalid_otel", "Duplicate OTLP attribute.")
                        attrs[key] = value.get(
                            "stringValue", value.get("boolValue", value.get("intValue"))
                        )
                    name = attrs.get("event.name")
                    kind, text, tool, status = None, None, None, None
                    if name == "codex.user_prompt":
                        kind, text = "user_message", attrs.get("prompt")
                    elif (
                        name == "codex.agent_response"
                        and attrs.get("agent.type") == "main"
                    ):
                        kind, text = "assistant_message", attrs.get("response")
                    elif name in {
                        "codex.tool_result",
                        "codex.tool_decision",
                        "codex.sandbox_outcome",
                    }:
                        kind, tool = "tool", attrs.get("tool_name")
                        status = attrs.get(
                            {
                                "codex.tool_result": "success",
                                "codex.tool_decision": "decision",
                                "codex.sandbox_outcome": "outcome",
                            }[name]
                        )
                        if type(status) is bool:
                            status = str(status).lower()
                    else:
                        ignored += 1
                        continue
                    if kind.endswith("message") and not isinstance(text, str):
                        raise APIError(
                            "invalid_otel", "Selected message has no text attribute."
                        )
                    identity = {
                        key: attrs.get(key)
                        for key in (
                            "event.timestamp",
                            "conversation.id",
                            "turn.id",
                            "item.id",
                            "call_id",
                            "tool_result_seq",
                        )
                    }
                    identity.update(
                        name=name,
                        kind=kind,
                        text=redact(text) if isinstance(text, str) else None,
                        tool=tool,
                        status=status,
                    )
                    events.append(
                        event(
                            {
                                "event_id": digest(identity),
                                "at": attrs.get("event.timestamp"),
                                "kind": kind,
                                "text": text,
                                "tool_name": tool,
                                "status": status,
                            }
                        )
                    )
    except (TypeError, KeyError, AttributeError) as error:
        raise APIError("invalid_otel", "Malformed OTLP log record.") from error
    return events, ignored
