"""Compose Resource Discovery identities with local Contx metadata."""

from __future__ import annotations

from uuid import UUID

from adapters.resource_discovery.contx_metadata import (
    CONTX_ENVIRONMENTS,
    CONTX_RESOURCE_TYPES,
    ContxMetadataError,
    ContxMetadataSource,
    ContxResourceQuery,
)
from workspaces.data_engineering.agents.resource_discovery import (
    IdentifierKind,
    ResourceDiscoverySource,
    ResourceIdentifier,
    ResourceRecord,
    client_name_index_key,
)


class ContxClientResourceResolver:
    """Resolve a client name, then query its effective Contx resources."""

    def __init__(
        self,
        identities: ResourceDiscoverySource,
        contx: ContxMetadataSource,
    ) -> None:
        """Compose identity lookup with local Contx metadata."""
        self.identities = identities
        self.contx = contx

    async def lookup(
        self,
        client_name: str,
        *,
        environment: str = "production",
        resource_type: str = "all",
        resource_kind: str | None = None,
    ) -> tuple[ResourceRecord, ...]:
        """Resolve one unique client name and return its effective resources."""
        identifier = ResourceIdentifier(IdentifierKind.CLIENT_NAME, client_name)
        identities = await self.identities.lookup(identifier)
        clients = _exact_clients(identities, client_name)
        if len(clients) > 1:
            raise ContxMetadataError.ambiguous_client(client_name)
        if clients:
            client_id, canonical_name = clients[0]
        else:
            client_id = await self.contx.resolve_client_id(
                client_name,
                environment=environment,
            )
            canonical_name = client_name
        return await self.contx.lookup(
            ContxResourceQuery(
                client_id=client_id,
                client_name=canonical_name,
                environment=environment,
                resource_type=resource_type,
                resource_kind=resource_kind,
            )
        )


def _exact_clients(
    records: tuple[ResourceRecord, ...],
    requested_name: str,
) -> tuple[tuple[str, str], ...]:
    requested_key = client_name_index_key(requested_name)
    clients: dict[str, str] = {}
    for record in records:
        client_id = record.get("provisioned_client_id")
        client_name = record.get("client_name")
        if (
            not isinstance(client_id, str)
            or not isinstance(client_name, str)
            or client_name_index_key(client_name) != requested_key
        ):
            continue
        try:
            normalized = str(UUID(client_id))
        except ValueError:
            continue
        clients[normalized] = client_name
    return tuple(sorted(clients.items()))


__all__ = [
    "CONTX_ENVIRONMENTS",
    "CONTX_RESOURCE_TYPES",
    "ContxClientResourceResolver",
    "ContxMetadataError",
    "ContxMetadataSource",
    "ContxResourceQuery",
]
