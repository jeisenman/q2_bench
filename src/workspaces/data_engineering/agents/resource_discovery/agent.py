"""Framework-neutral read-only resource discovery agent."""

from __future__ import annotations

from collections.abc import Mapping

from domain import AgentDefinition, AgentRequest, AgentResult, ToolDefinition
from workspaces.data_engineering.agents.resource_discovery.models import (
    IdentifierKind,
    ResourceIdentifier,
    ResourceMetadata,
    ResourceSearch,
)
from workspaces.data_engineering.agents.resource_discovery.ports import (
    ResourceDiscoverySource,
)
from workspaces.data_engineering.agents.resource_discovery.reporting import (
    render_search,
)

RESOURCE_DISCOVERY_V1_DEFINITION = AgentDefinition(
    name="resource-discovery",
    description="Find non-secret client and resource metadata by identifier.",
    instructions=(
        "Search the injected read-only source using the supplied structured "
        "identifier. A client_id must be the complete client UUID, never its "
        "three-character report prefix. Return only allowlisted non-secret "
        "metadata. Report zero, one, or multiple matches explicitly; never "
        "infer a client or expose credentials."
    ),
    tools=(
        ToolDefinition(
            name="ResourceDiscovery",
            description="Search non-secret resource metadata by one identifier.",
            input_schema=(
                ("identifier", "string"),
                ("identifier_kind", "string"),
                ("identifier_value", "complete UUID when kind is client_id"),
            ),
        ),
    ),
    version="1",
)

# Stable short name for callers that do not need the version suffix.
RESOURCE_DISCOVERY_DEFINITION = RESOURCE_DISCOVERY_V1_DEFINITION


class ResourceDiscoveryError(RuntimeError):
    """Raised when a resource discovery request cannot complete safely."""


def _request_identifier(request: AgentRequest) -> ResourceIdentifier:
    """Build a structured identifier without inferring from the prompt."""
    values: dict[str, object] = {}
    for name, value in request.attributes:
        if name in values:
            message = f"request attribute {name!r} is duplicated"
            raise ValueError(message)
        values[name] = value

    identifier_value = values.get("identifier")
    if identifier_value is None:
        kind_value = values.get("identifier_kind")
        identifier_value = values.get("identifier_value")
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


def _metadata_sort_key(metadata: ResourceMetadata) -> tuple[str, ...]:
    """Return the stable field order used for deterministic reports."""
    return tuple(
        value or ""
        for value in (
            metadata.client_name,
            metadata.provisioned_client_id,
            metadata.client_id,
            metadata.resource_id,
            metadata.resource_name,
            metadata.resource_type,
            metadata.subdomain,
            metadata.environment,
            metadata.zone,
            metadata.service,
            metadata.resource_set,
            metadata.database,
            metadata.storage,
            metadata.datalake,
            metadata.reviewed_production_resend_url,
            metadata.routing_source,
            str(metadata.prod_support_ignore),
        )
    )


async def _await_records(
    source: ResourceDiscoverySource,
    identifier: ResourceIdentifier,
) -> tuple[Mapping[str, object], ...]:
    """Await the injected source and preserve provider failures."""
    return await source.lookup(identifier)


class ResourceDiscoveryAgent:
    """Search injected metadata without network, framework, or write effects."""

    def __init__(self, source: ResourceDiscoverySource) -> None:
        """Create an agent with a read-only metadata source."""
        if source is None:
            message = "source must implement ResourceDiscoverySource"
            raise TypeError(message)
        self._source = source

    @property
    def definition(self) -> AgentDefinition:
        """Return the immutable version-one agent definition."""
        return RESOURCE_DISCOVERY_V1_DEFINITION

    async def search(self, identifier: ResourceIdentifier) -> ResourceSearch:
        """Search and deterministically order all source matches."""
        records = await _await_records(self._source, identifier)
        try:
            matches = tuple(ResourceMetadata.from_record(record) for record in records)
        except (TypeError, ValueError) as error:
            message = f"invalid resource metadata: {error}"
            raise ResourceDiscoveryError(message) from error
        return ResourceSearch(
            identifier=identifier,
            matches=tuple(sorted(matches, key=_metadata_sort_key)),
        )

    async def run(self, request: AgentRequest) -> AgentResult:
        """Run a structured search request and render its safe report."""
        try:
            identifier = _request_identifier(request)
        except (TypeError, ValueError) as error:
            message = f"invalid identifier: {error}"
            raise ResourceDiscoveryError(message) from error
        try:
            search = await self.search(identifier)
        except ResourceDiscoveryError:
            raise
        except Exception as error:
            message = str(error) or "resource discovery source failed"
            raise ResourceDiscoveryError(message) from error
        unique = search.matches[0] if len(search.matches) == 1 else None
        return AgentResult(
            output=render_search(search),
            correlation_id=request.correlation_id,
            tool_calls=("ResourceDiscovery",),
            attributes=(
                ("agent_version", "1"),
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
                    (
                        unique.reviewed_production_resend_url
                        if unique is not None
                        else None
                    ),
                ),
                (
                    "routing_source",
                    unique.routing_source if unique is not None else None,
                ),
                (
                    "prod_support_ignore",
                    unique.prod_support_ignore if unique is not None else False,
                ),
            ),
        )
