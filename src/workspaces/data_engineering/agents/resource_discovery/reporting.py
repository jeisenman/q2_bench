"""Deterministic rendering for resource discovery results."""

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
        "Version: v1",
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
