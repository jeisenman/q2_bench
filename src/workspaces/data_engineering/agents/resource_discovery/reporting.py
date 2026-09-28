"""Deterministic rendering for resource discovery and alias-memory results."""

from agent_memory import EvidenceOutcome, MemoryRecord, MemoryStatus
from domain import AgentResult
from workspaces.data_engineering.agents.resource_discovery.models import (
    ResourceMetadata,
    ResourceSearch,
    SearchStatus,
)

_DISPLAY_FIELDS: tuple[tuple[str, str], ...] = (
    ("Client name", "client_name"),
    ("Provisioned client ID", "provisioned_client_id"),
    ("Client ID", "client_id"),
    ("Subdomain", "subdomain"),
    ("Environment", "environment"),
    ("Zone", "zone"),
    ("Service", "service"),
    ("Resource set", "resource_set"),
    ("Resource ID", "resource_id"),
    ("Resource name", "resource_name"),
    ("Resource type", "resource_type"),
    ("Database", "database"),
    ("Storage", "storage"),
    ("DataLake", "datalake"),
    ("Reviewed resend URL", "reviewed_production_resend_url"),
    ("Routing source", "routing_source"),
)


def _render_metadata(metadata: ResourceMetadata) -> list[str]:
    """Render only the fixed allowlist of non-secret fields."""
    lines = ["Resource Discovery:"]
    for label, field_name in _DISPLAY_FIELDS:
        value = getattr(metadata, field_name)
        if value is not None:
            lines.append(f"- {label}: {value}")
    if metadata.prod_support_ignore:
        lines.append("- Production support: ignored by reviewed configuration")
    return lines


def render_search(search: ResourceSearch) -> str:
    """Render one search with explicit not-found and ambiguity handling."""
    lines = [
        "# Resource Discovery",
        "",
        "Version: v2",
        f"Identifier: {search.identifier.value}",
        "",
    ]
    if search.status is SearchStatus.NOT_FOUND:
        lines.extend(
            (
                "Finding: no unique match",
                "Resource Discovery:",
                "- No unique match was returned.",
                "",
                "Ambiguities:",
                "- None.",
            )
        )
        return "\n".join(lines)

    if search.status is SearchStatus.AMBIGUOUS:
        lines.extend(("Finding: Ambiguous matches", ""))
    else:
        lines.extend(("Finding: unique match", ""))
    for index, metadata in enumerate(search.matches):
        if index:
            lines.extend(("", f"Match {index + 1}:"))
        lines.extend(_render_metadata(metadata))
    lines.extend(("", "Ambiguities:"))
    if search.status is SearchStatus.AMBIGUOUS:
        lines.append("- Multiple records matched; provide a more specific identifier.")
    else:
        lines.append("- None.")
    return "\n".join(lines)


def search_result(
    search: ResourceSearch,
    correlation_id: str,
    *,
    extra_attributes: tuple[tuple[str, str], ...] = (),
) -> AgentResult:
    """Return the standard safe result for a resource search."""
    unique = search.matches[0] if len(search.matches) == 1 else None
    return AgentResult(
        output=render_search(search),
        correlation_id=correlation_id,
        tool_calls=("ResourceDiscovery",),
        attributes=(
            ("agent_version", "2"),
            ("identifier_kind", search.identifier.kind.value),
            ("identifier_value", search.identifier.value),
            ("status", search.status.value),
            ("match_count", len(search.matches)),
            ("client_name", unique.client_name if unique is not None else None),
            (
                "provisioned_client_id",
                unique.provisioned_client_id if unique is not None else None,
            ),
            ("environment", unique.environment if unique is not None else None),
            (
                "reviewed_production_resend_url",
                (unique.reviewed_production_resend_url if unique is not None else None),
            ),
            (
                "routing_source",
                unique.routing_source if unique is not None else None,
            ),
            (
                "prod_support_ignore",
                unique.prod_support_ignore if unique is not None else False,
            ),
            *extra_attributes,
        ),
    )


def confirmation_result(memory: MemoryRecord, correlation_id: str) -> AgentResult:
    """Ask the caller to confirm one proposed canonical alias."""
    metadata = memory.metadata_mapping
    name = metadata["canonical_name"]
    canonical_id = metadata["canonical_entity_id"]
    return AgentResult(
        output=(
            f"By {memory.key}, do you mean {name} ({canonical_id})?\n"
            f"Confirm memory {memory.memory_id}."
        ),
        correlation_id=correlation_id,
        tool_calls=("ResourceDiscovery",),
        attributes=(
            ("status", "confirmation_required"),
            ("memory_id", str(memory.memory_id)),
            ("memory_status", memory.status.value),
            ("memory_evidence_count", memory.evidence_count),
            ("candidate_client_name", name),
            ("candidate_provisioned_client_id", canonical_id),
        ),
    )


def feedback_output(
    memory: MemoryRecord,
    outcome: EvidenceOutcome,
    promote_after: int,
) -> str:
    """Render the result of explicit alias feedback."""
    if outcome is EvidenceOutcome.REJECTED:
        return f"Rejected alias memory {memory.memory_id}."
    if memory.status is MemoryStatus.CONFIRMED:
        return f"Confirmed alias memory {memory.memory_id}; future lookups may resolve."
    return (
        f"Recorded confirmation {memory.evidence_count}/{promote_after} for "
        f"alias memory {memory.memory_id}."
    )
