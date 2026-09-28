"""Parse bounded Resource Discovery requests and memory feedback."""

from __future__ import annotations

import re
from collections.abc import Mapping
from uuid import UUID

from agent_memory import EvidenceOutcome
from domain import AgentRequest
from workspaces.data_engineering.agents.resource_discovery.models import (
    IdentifierKind,
    ResourceIdentifier,
)

LOOKUP_PROMPT = re.compile(
    r"^\s*(?:find|lookup|look\s+up|resolve|get|show)\s+"
    r"(?:the\s+)?(?:client\s+)?(?P<mention>.+?)\s*[?!.]*\s*$",
    re.IGNORECASE,
)


def request_values(request: AgentRequest) -> dict[str, object]:
    """Return unique request attributes."""
    values: dict[str, object] = {}
    for name, value in request.attributes:
        if name in values:
            message = f"request attribute {name!r} is duplicated"
            raise ValueError(message)
        values[name] = value
    return values


def request_identifier(
    request: AgentRequest,
    values: Mapping[str, object],
) -> ResourceIdentifier:
    """Build a structured identifier or parse one bounded lookup prompt."""
    identifier_value = values.get("identifier")
    if identifier_value is None:
        kind_value = values.get("identifier_kind")
        identifier_value = values.get("identifier_value")
        if kind_value is None and identifier_value is None:
            match = LOOKUP_PROMPT.fullmatch(request.prompt)
            if match is None:
                message = (
                    "request must include identifier attributes or use "
                    "'find <client>' lookup wording"
                )
                raise ValueError(message)
            return ResourceIdentifier(
                kind=IdentifierKind.CLIENT_NAME,
                value=match.group("mention"),
            )
        if not isinstance(kind_value, str):
            message = "request must include string attribute 'identifier_kind'"
            raise TypeError(message)
        try:
            kind = IdentifierKind(kind_value)
        except ValueError as error:
            allowed = ", ".join(item.value for item in IdentifierKind)
            message = f"identifier_kind must be one of: {allowed}"
            raise ValueError(message) from error
    else:
        kind = IdentifierKind.RESOURCE_ID
    if not isinstance(identifier_value, str):
        message = "request must include string attribute 'identifier'"
        raise TypeError(message)
    return ResourceIdentifier(kind=kind, value=identifier_value)


def memory_feedback(
    values: Mapping[str, object],
) -> tuple[UUID, EvidenceOutcome] | None:
    """Parse explicit alias-memory confirmation attributes."""
    memory_id = values.get("memory_id")
    outcome = values.get("memory_outcome")
    if memory_id is None and outcome is None:
        return None
    if not isinstance(memory_id, str):
        message = "memory_id must be a UUID string"
        raise TypeError(message)
    if not isinstance(outcome, str):
        message = "memory_outcome must be 'confirmed' or 'rejected'"
        raise TypeError(message)
    try:
        return UUID(memory_id), EvidenceOutcome(outcome)
    except ValueError as error:
        message = "memory confirmation attributes are invalid"
        raise ValueError(message) from error
