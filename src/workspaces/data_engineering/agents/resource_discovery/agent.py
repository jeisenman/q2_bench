"""Framework-neutral read-only resource discovery agent."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from agent_memory import AgentMemory, AliasResolutionStatus, EvidenceOutcome
from domain import AgentDefinition, AgentRequest, AgentResult, ToolDefinition
from observability import traced_agent_run
from workspaces.data_engineering.agents.resource_discovery.models import (
    IdentifierKind,
    ResourceIdentifier,
    ResourceMetadata,
    ResourceSearch,
    SearchStatus,
)
from workspaces.data_engineering.agents.resource_discovery.ports import (
    ResourceAliasCandidateSource,
    ResourceDiscoverySource,
    ResourceLocalLookupSource,
)
from workspaces.data_engineering.agents.resource_discovery.reporting import (
    confirmation_result,
    feedback_output,
    search_result,
)
from workspaces.data_engineering.agents.resource_discovery.request import (
    memory_feedback,
    request_identifier,
    request_values,
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

RESOURCE_DISCOVERY_V2_DEFINITION = AgentDefinition(
    name="resource-discovery",
    description="Resolve resources through local identity data and scoped memory.",
    instructions=(
        "Short-circuit exact client identifiers through the authoritative local "
        "JSON index. Use confirmed scoped alias memory only to identify the "
        "canonical client UUID, then dereference that UUID through Resource "
        "Discovery. For a unique unconfirmed acronym candidate, ask the caller "
        "to confirm it. Never learn from raw prompts, infer ambiguous clients, "
        "or expose credentials."
    ),
    tools=(
        ToolDefinition(
            name="ResourceDiscovery",
            description="Resolve safe resource metadata and confirmed aliases.",
            input_schema=(
                ("identifier", "string"),
                ("identifier_kind", "string"),
                ("identifier_value", "complete UUID when kind is client_id"),
                ("memory_id", "UUID returned by an alias proposal"),
                ("memory_outcome", "confirmed or rejected"),
            ),
        ),
    ),
    version="2",
)

# Stable short name for callers that do not need the version suffix.
RESOURCE_DISCOVERY_DEFINITION = RESOURCE_DISCOVERY_V2_DEFINITION


class ResourceDiscoveryError(RuntimeError):
    """Raised when a resource discovery request cannot complete safely."""


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

    def __init__(
        self,
        source: ResourceDiscoverySource,
        *,
        memory: AgentMemory | None = None,
    ) -> None:
        """Create an agent with a read-only metadata source."""
        if source is None:
            message = "source must implement ResourceDiscoverySource"
            raise TypeError(message)
        self._source = source
        self._memory = memory

    @property
    def definition(self) -> AgentDefinition:
        """Return the current immutable agent definition."""
        return RESOURCE_DISCOVERY_V2_DEFINITION

    async def search(self, identifier: ResourceIdentifier) -> ResourceSearch:
        """Search and deterministically order all source matches."""
        records = await _await_records(self._source, identifier)
        return _search_from_records(identifier, records)

    async def _search_local(
        self,
        identifier: ResourceIdentifier,
    ) -> ResourceSearch | None:
        if not isinstance(self._source, ResourceLocalLookupSource):
            return None
        records = await self._source.lookup_local(identifier)
        return _search_from_records(identifier, records)

    @traced_agent_run
    async def run(self, request: AgentRequest) -> AgentResult:
        """Run a structured search request and render its safe report."""
        try:
            values = request_values(request)
            feedback = memory_feedback(values)
            if feedback is not None:
                return await self._record_memory_feedback(request, *feedback)
            identifier = request_identifier(request, values)
        except (TypeError, ValueError) as error:
            message = f"invalid identifier: {error}"
            raise ResourceDiscoveryError(message) from error
        try:
            if (
                identifier.kind is IdentifierKind.CLIENT_NAME
                and self._memory is not None
            ):
                local_search = await self._search_local(identifier)
                if (
                    local_search is not None
                    and local_search.status is SearchStatus.UNIQUE
                ):
                    return search_result(local_search, request.correlation_id)
                memory_result = await self._resolve_memory(request, identifier)
                if memory_result is not None:
                    return memory_result
            search = await self.search(identifier)
        except ResourceDiscoveryError:
            raise
        except Exception as error:
            message = str(error) or "resource discovery source failed"
            raise ResourceDiscoveryError(message) from error
        return search_result(search, request.correlation_id)

    async def _resolve_memory(
        self,
        request: AgentRequest,
        identifier: ResourceIdentifier,
    ) -> AgentResult | None:
        """Resolve or propose one client alias through scoped agent memory."""
        assert self._memory is not None
        resolution = await self._memory.resolve_alias(identifier.value)
        if resolution.status is AliasResolutionStatus.RESOLVED:
            memory = resolution.unique
            assert memory is not None
            canonical_id = memory.metadata_mapping.get("canonical_entity_id")
            if canonical_id is None:
                message = f"alias memory {memory.memory_id} has no canonical ID"
                raise ResourceDiscoveryError(message)
            search = await self.search(
                ResourceIdentifier(IdentifierKind.CLIENT_ID, canonical_id)
            )
            return search_result(
                search,
                request.correlation_id,
                extra_attributes=(("memory_resolution", "confirmed"),),
            )
        if resolution.status is AliasResolutionStatus.CONFIRMATION_REQUIRED:
            memory = resolution.unique
            assert memory is not None
            return confirmation_result(memory, request.correlation_id)
        if resolution.status is AliasResolutionStatus.AMBIGUOUS:
            message = f"alias {identifier.value!r} has conflicting active memories"
            raise ResourceDiscoveryError(message)
        if not isinstance(self._source, ResourceAliasCandidateSource):
            return None
        records = await self._source.alias_candidates(identifier.value)
        if len(records) != 1:
            return None
        candidate = ResourceMetadata.from_record(records[0])
        if candidate.client_name is None or candidate.provisioned_client_id is None:
            return None
        memory = await self._memory.propose_alias(
            alias=identifier.value,
            canonical_entity_type="resource-discovery-client",
            canonical_entity_id=candidate.provisioned_client_id,
            canonical_name=candidate.client_name,
        )
        return confirmation_result(memory, request.correlation_id)

    async def _record_memory_feedback(
        self,
        request: AgentRequest,
        memory_id: UUID,
        outcome: EvidenceOutcome,
    ) -> AgentResult:
        """Record explicit user feedback without storing the raw prompt."""
        if self._memory is None:
            message = "resource discovery memory is not configured"
            raise ResourceDiscoveryError(message)
        memory = await self._memory.record_alias_evidence(
            memory_id,
            outcome,
            correlation_id=request.correlation_id,
        )
        return AgentResult(
            output=feedback_output(memory, outcome, self._memory.alias_confirmations),
            correlation_id=request.correlation_id,
            tool_calls=("ResourceDiscovery",),
            attributes=(
                ("memory_id", str(memory.memory_id)),
                ("memory_status", memory.status.value),
                ("memory_evidence_count", memory.evidence_count),
            ),
        )


def _search_from_records(
    identifier: ResourceIdentifier,
    records: tuple[Mapping[str, object], ...],
) -> ResourceSearch:
    """Validate, sanitize, and deterministically order provider records."""
    try:
        matches = tuple(ResourceMetadata.from_record(record) for record in records)
    except (TypeError, ValueError) as error:
        message = f"invalid resource metadata: {error}"
        raise ResourceDiscoveryError(message) from error
    return ResourceSearch(
        identifier=identifier,
        matches=tuple(sorted(matches, key=_metadata_sort_key)),
    )
