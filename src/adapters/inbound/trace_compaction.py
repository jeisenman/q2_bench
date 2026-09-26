"""Bound model-judge trace context while preserving useful evidence."""

from __future__ import annotations

import json
import re

TRACE_PROMPT_LIMIT = 50_000
TRACE_TEXT_LIMIT = 2_000
TRACE_EVENT_LIMIT = 100
REDACTED = "[REDACTED]"
SENSITIVE_KEY = re.compile(
    r"(?:authorization|credential|password|secret|"
    r"(?:access|refresh|session)[_-]?token|api[_-]?key|"
    r"access[_-]?key|private[_-]?key)",
    re.IGNORECASE,
)
SENSITIVE_TEXT = (
    re.compile(
        r"(?i)((?:authorization|credential|password|secret|"
        r"(?:access|refresh|session)[_-]?token|api[_-]?key|"
        r"access[_-]?key(?:_id)?|private[_-]?key)"
        r"[\"']?\s*[=:]\s*[\"']?)"
        r"[^\"'\r\n,}]+"
    ),
    re.compile(r"(?i)(aws_access_key_id[\"']?\s*[=:]\s*[\"']?)[^\"'\s,}]+"),
    re.compile(r"(?i)(aws_secret_access_key[\"']?\s*[=:]\s*[\"']?)[^\"'\s,}]+"),
    re.compile(r"(?i)(aws_session_token[\"']?\s*[=:]\s*[\"']?)[^\"'\s,}]+"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
)


def compact_trace_for_judge(
    events: tuple[dict[str, object], ...],
) -> tuple[dict[str, object], ...]:
    """Retain completed events and clip oversized text fields."""
    compacted: list[dict[str, object]] = []
    characters = 0
    for event in events:
        item = event.get("item")
        if event.get("type") == "item.started":
            continue
        if isinstance(item, dict) and _is_ignored_runtime_warning(item):
            continue
        compact = _compact_mapping(event)
        encoded = json.dumps(compact, sort_keys=True)
        if characters + len(encoded) > TRACE_PROMPT_LIMIT:
            continue
        compacted.append(compact)
        characters += len(encoded)
        if len(compacted) >= TRACE_EVENT_LIMIT:
            break
    return tuple(compacted)


def _compact_mapping(value: dict[str, object]) -> dict[str, object]:
    return {
        key: REDACTED if SENSITIVE_KEY.search(key) else _compact_value(item)
        for key, item in value.items()
    }


def _compact_value(value: object) -> object:
    if isinstance(value, str):
        redacted = redact_text(value)
        if len(redacted) <= TRACE_TEXT_LIMIT:
            return redacted
        retained = TRACE_TEXT_LIMIT // 2
        omitted = len(redacted) - (retained * 2)
        return (
            f"{redacted[:retained]}\n...[{omitted} characters omitted]...\n"
            f"{redacted[-retained:]}"
        )
    if isinstance(value, dict):
        return _compact_mapping(value)
    if isinstance(value, list):
        return [_compact_value(item) for item in value]
    return value


def redact_text(value: str) -> str:
    """Remove common credential forms before trace or report persistence."""
    redacted = value
    for pattern in SENSITIVE_TEXT:
        redacted = pattern.sub(
            lambda match: (
                f"{match.group(1)}{REDACTED}" if match.lastindex else REDACTED
            ),
            redacted,
        )
    return redacted


def _is_ignored_runtime_warning(item: dict[str, object]) -> bool:
    message = item.get("message")
    return (
        item.get("type") == "error"
        and isinstance(message, str)
        and "unrecognized configuration settings" in message
    )
