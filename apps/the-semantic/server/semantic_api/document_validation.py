"""Bounded contracts for local, versioned document edits."""

import json
from typing import Any
from uuid import UUID

from . import validation as valid

KINDS = ("proposal", "research", "agent", "sme")
PROSE = {"title", "question", "hypothesis", "plan"}
AGENT_FIELDS = {
    "id",
    "version",
    "name",
    "purpose",
    "instructions",
    "model",
    "allowed_tools",
    "page_plugin",
}


def identity(kind: Any, document_id: Any) -> tuple[str, str]:
    """Validate an existing source identity or a stable local SME node identity."""
    if kind not in KINDS:
        raise valid.APIError("invalid_kind", "Document kind is unsupported.")
    if kind == "sme":
        valid.string(document_id, 2048)
        try:
            node = json.loads(document_id)
        except (ValueError, TypeError) as error:
            raise valid.APIError(
                "invalid_id", "SME ID must contain node JSON."
            ) from error
        if (
            not isinstance(node, list)
            or len(node) != 3
            or not all(isinstance(part, str) for part in node)
            or not node[0].strip()
            or not node[1].strip()
        ):
            raise valid.APIError(
                "invalid_id", "SME ID must contain [namespace, name, column-or-empty]."
            )
    else:
        valid.identifier(document_id)
    return kind, document_id


def content(kind: str, value: Any) -> dict:
    """Validate only the editable fields for each supported document kind."""
    if kind == "agent":
        return valid.agent(value)
    if kind == "sme":
        valid.shape(value, {"text", "source_commit"})
        valid.string(value["text"])
        if value["source_commit"] is not None:
            valid.string(value["source_commit"], 128)
        return value
    valid.shape(value, PROSE | ({"output"} if kind == "research" else set()))
    for field in PROSE:
        valid.string(
            value[field], 1000 if field == "title" and kind == "proposal" else 16000
        )
    if kind == "research" and value["output"] is not None:
        valid.string(value["output"], 200000, empty=True)
    return value


def save(value: Any) -> dict:
    """Require an exact save request with a safe UUID and nonnegative base."""
    valid.shape(value, {"kind", "id", "base_version", "content", "idempotency_key"})
    identity(value["kind"], value["id"])
    if type(value["base_version"]) is not int or value["base_version"] < 0:
        raise valid.APIError(
            "invalid_version", "base_version must be a nonnegative integer."
        )
    key = value["idempotency_key"]
    try:
        if not isinstance(key, str) or str(UUID(key)) != key.lower():
            raise ValueError
    except (ValueError, AttributeError) as error:
        raise valid.APIError(
            "invalid_idempotency_key", "Use a canonical UUID idempotency key."
        ) from error
    content(value["kind"], value["content"])
    return value
