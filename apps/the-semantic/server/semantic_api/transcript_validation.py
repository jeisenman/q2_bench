"""Strict text-only contracts for explicitly imported historical evidence."""

import json
import re
from datetime import datetime

from .validation import APIError, identifier, shape, string

MAX_BYTES = 1024 * 1024
MAX_ITEMS = 1000
MAX_TEXT = 256 * 1024


def timestamp(value: object) -> None:
    """Require an ISO timestamp with an explicit timezone."""
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)", value
    ):
        raise APIError(
            "invalid_timestamp", "Timestamp requires ISO date, time and offset."
        )
    try:
        datetime.fromisoformat(value)
    except ValueError as error:
        raise APIError(
            "invalid_timestamp", "Timestamp is not a valid date and time."
        ) from error


def transcript(value: object) -> dict:
    """Validate captured public messages and paired tool evidence without execution."""
    shape(value, {"source", "thread_id", "title", "description", "redactions", "items"})
    if value["source"] != "Native Codex rollout JSONL":
        raise APIError(
            "invalid_source", "Only Native Codex rollout JSONL is supported."
        )
    identifier(value["thread_id"])
    string(value["title"], 1000)
    string(value["description"], 16000)
    shape(value["redactions"], set())
    items = value["items"]
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS:
        raise APIError("limit_exceeded", "Transcript requires 1..1000 items.")
    calls, outputs = set(), set()
    for item in items:
        if not isinstance(item, dict):
            raise APIError("invalid_item", "Transcript items must be objects.")
        kind = item.get("type")
        if kind == "message":
            _message(item)
        elif kind == "tool_call":
            shape(item, {"timestamp", "type", "call_id", "name", "arguments", "status"})
            identifier(item["call_id"])
            string(item["name"], 256)
            string(item["arguments"], MAX_TEXT, empty=True)
            if item["status"] not in (None, "completed") or item["call_id"] in calls:
                raise APIError(
                    "invalid_call",
                    "Tool calls require unique IDs and a supported status.",
                )
            calls.add(item["call_id"])
        elif kind == "tool_output":
            shape(item, {"timestamp", "type", "call_id", "output"})
            identifier(item["call_id"])
            output = item["output"]
            if isinstance(output, list) and 1 <= len(output) <= 100:
                for block in output:
                    shape(block, {"type", "text"})
                    if block["type"] != "input_text":
                        raise APIError(
                            "invalid_output", "Tool output blocks must be input_text."
                        )
                    string(block["text"], MAX_TEXT, empty=True)
            else:
                string(output, MAX_TEXT, empty=True)
            if item["call_id"] not in calls or item["call_id"] in outputs:
                raise APIError(
                    "invalid_output",
                    "Tool output requires one preceding unmatched call.",
                )
            outputs.add(item["call_id"])
        else:
            raise APIError(
                "invalid_item",
                "Only messages, tool calls and tool outputs are supported.",
            )
        timestamp(item["timestamp"])
    if calls != outputs:
        raise APIError("invalid_output", "Every tool call requires one output.")
    if (
        len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())
        > MAX_BYTES
    ):
        raise APIError("limit_exceeded", "Transcript exceeds 1 MiB of UTF-8 JSON.")
    return value


def _message(item: dict) -> None:
    shape(item, {"timestamp", "type", "role", "phase", "content"})
    role = item["role"]
    phases = (
        (None,) if role == "user" else (None, "commentary", "final", "final_answer")
    )
    if role not in ("user", "assistant") or item["phase"] not in phases:
        raise APIError(
            "invalid_message", "Only public user and assistant phases are supported."
        )
    content = item["content"]
    if not isinstance(content, list) or not 1 <= len(content) <= 100:
        raise APIError("invalid_content", "Message requires 1..100 text blocks.")
    for block in content:
        shape(block, {"type", "text"})
        if block["type"] != ("input_text" if role == "user" else "output_text"):
            raise APIError(
                "invalid_content", "Content must be public role-appropriate text."
            )
        string(block["text"], MAX_TEXT, empty=True)
