"""Read-only adapter for the PrecisionLender Resource Discovery API."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from workspaces.data_engineering.agents.resource_discovery import (
    IdentifierKind,
    ResourceIdentifier,
    ResourceRecord,
    parse_client_name,
)

TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"


class ResourceDiscoveryApiError(RuntimeError):
    """Raised when Resource Discovery configuration or responses are invalid."""

    @classmethod
    def invalid_json(cls) -> ResourceDiscoveryApiError:
        """Return an error for a non-JSON HTTP response."""
        return cls("Resource Discovery response must be valid JSON")

    @classmethod
    def invalid_token_response(cls) -> ResourceDiscoveryApiError:
        """Return an error for a non-object token response."""
        return cls("Resource Discovery token response must be an object")

    @classmethod
    def missing_access_token(cls) -> ResourceDiscoveryApiError:
        """Return an error for a token response without a usable token."""
        return cls("Resource Discovery token response is missing access_token")

    @classmethod
    def invalid_search_response(cls) -> ResourceDiscoveryApiError:
        """Return an error for an unsupported search response shape."""
        return cls(
            "Resource Discovery search response must be an object or list of objects"
        )


@dataclass(frozen=True, slots=True)
class ResourceDiscoveryConfig:
    """Connection settings for the production Resource Discovery API."""

    base_url: str
    tenant_id: str
    client_id: str
    client_secret: str
    scope: str


class ResourceDiscoveryTransport(Protocol):
    """Small HTTP boundary for Resource Discovery authentication and reads."""

    def request(
        self,
        request: Request,
    ) -> object:
        """Execute one HTTP request and decode its JSON response."""


class UrllibResourceDiscoveryTransport:
    """Resource Discovery transport implemented with the standard library."""

    def request(self, request: Request) -> object:
        """Execute one request with a bounded timeout."""
        with urlopen(request, timeout=30) as response:
            payload = response.read()
        try:
            return json.loads(payload)
        except json.JSONDecodeError as error:
            raise ResourceDiscoveryApiError.invalid_json() from error


class ResourceDiscoveryApiSource:
    """Search genuine non-secret resource metadata through read-only GETs."""

    def __init__(
        self,
        config: ResourceDiscoveryConfig,
        transport: ResourceDiscoveryTransport | None = None,
    ) -> None:
        """Initialize with explicit Azure and API connection settings."""
        self._config = config
        self._transport = transport or UrllibResourceDiscoveryTransport()

    @classmethod
    def from_environment(cls) -> ResourceDiscoveryApiSource:
        """Load all required production settings and fail on missing values."""
        names = (
            "RESOURCE_DISCOVERY_BASE_URL",
            "RESOURCE_DISCOVERY_TENANT_ID",
            "RESOURCE_DISCOVERY_CLIENT_ID",
            "RESOURCE_DISCOVERY_CLIENT_SECRET",
            "RESOURCE_DISCOVERY_SCOPE",
        )
        values = {name: os.environ.get(name) for name in names}
        missing = tuple(name for name, value in values.items() if not value)
        if missing:
            message = "missing Resource Discovery configuration: " + ", ".join(missing)
            raise ResourceDiscoveryApiError(message)
        return cls(
            ResourceDiscoveryConfig(
                base_url=values["RESOURCE_DISCOVERY_BASE_URL"] or "",
                tenant_id=values["RESOURCE_DISCOVERY_TENANT_ID"] or "",
                client_id=values["RESOURCE_DISCOVERY_CLIENT_ID"] or "",
                client_secret=values["RESOURCE_DISCOVERY_CLIENT_SECRET"] or "",
                scope=values["RESOURCE_DISCOVERY_SCOPE"] or "",
            )
        )

    async def lookup(
        self,
        identifier: ResourceIdentifier,
    ) -> tuple[ResourceRecord, ...]:
        """Return all API records matching one explicit identifier."""
        return await asyncio.to_thread(self._lookup, identifier)

    async def lookup_batch(
        self,
        identifiers: tuple[ResourceIdentifier, ...],
    ) -> tuple[tuple[ResourceRecord, ...], ...]:
        """Resolve identifiers with one access-token request."""
        return await asyncio.to_thread(self._lookup_batch, identifiers)

    def _lookup(
        self,
        identifier: ResourceIdentifier,
    ) -> tuple[ResourceRecord, ...]:
        token = self._access_token()
        return self._lookup_with_token(identifier, token)

    def _lookup_batch(
        self,
        identifiers: tuple[ResourceIdentifier, ...],
    ) -> tuple[tuple[ResourceRecord, ...], ...]:
        token = self._access_token()
        return tuple(
            self._lookup_with_token(identifier, token) for identifier in identifiers
        )

    def _lookup_with_token(
        self,
        identifier: ResourceIdentifier,
        token: str,
    ) -> tuple[ResourceRecord, ...]:
        path, query_name = _query(identifier.kind)
        query = urlencode({query_name: identifier.value})
        url = urljoin(
            self._config.base_url.rstrip("/") + "/",
            path.lstrip("/"),
        )
        request = Request(
            f"{url}?{query}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            method="GET",
        )
        response = self._transport.request(request)
        return tuple(_normalize_record(record) for record in _records(response))

    def _access_token(self) -> str:
        body = urlencode(
            {
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret,
                "grant_type": "client_credentials",
                "scope": self._config.scope,
            }
        ).encode()
        request = Request(
            TOKEN_URL.format(tenant_id=self._config.tenant_id),
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        response = self._transport.request(request)
        if not isinstance(response, Mapping):
            raise ResourceDiscoveryApiError.invalid_token_response()
        token = response.get("access_token")
        if not isinstance(token, str) or not token:
            raise ResourceDiscoveryApiError.missing_access_token()
        return token


def _query(kind: IdentifierKind) -> tuple[str, str]:
    """Map domain identifier kinds to documented API filters."""
    clients = {
        IdentifierKind.CLIENT_ID: "provisionedClientId",
        IdentifierKind.CLIENT_NAME: "name",
        IdentifierKind.SUBDOMAIN: "subdomain",
    }
    if kind in clients:
        return "/api/v1/clients", clients[kind]
    resources = {
        IdentifierKind.RESOURCE_ID: "id",
        IdentifierKind.RESOURCE_SET: "resourceSet",
        IdentifierKind.ENVIRONMENT: "environment",
        IdentifierKind.DATABASE: "database",
        IdentifierKind.STORAGE: "storage",
        IdentifierKind.DATALAKE: "datalake",
    }
    return "/api/v1/resources", resources[kind]


def _records(payload: object) -> tuple[Mapping[str, object], ...]:
    """Validate supported single-record and list response shapes."""
    if isinstance(payload, Mapping):
        return (payload,)
    if isinstance(payload, list) and all(isinstance(item, Mapping) for item in payload):
        return tuple(payload)
    raise ResourceDiscoveryApiError.invalid_search_response()


def _normalize_record(record: Mapping[str, object]) -> ResourceRecord:
    """Normalize documented API names into the domain allowlist."""
    aliases = {
        "id": "resource_id",
        "resourceId": "resource_id",
        "resourceName": "resource_name",
        "resourceType": "resource_type",
        "provisionedClientId": "provisioned_client_id",
        "clientId": "client_id",
        "name": "client_name",
        "clientName": "client_name",
        "resourceSet": "resource_set",
        "storageAccount": "storage",
        "dataLake": "datalake",
        "dataLakeAccount": "datalake",
        "reviewedProductionResendUrl": "reviewed_production_resend_url",
        "routingSource": "routing_source",
        "prodSupportIgnore": "prod_support_ignore",
    }
    normalized = {
        aliases.get(name, name): value
        for name, value in record.items()
        if aliases.get(name, name)
        in {
            "resource_id",
            "resource_name",
            "resource_type",
            "provisioned_client_id",
            "client_id",
            "client_name",
            "subdomain",
            "environment",
            "zone",
            "service",
            "resource_set",
            "database",
            "storage",
            "datalake",
            "reviewed_production_resend_url",
            "routing_source",
            "prod_support_ignore",
        }
    }
    client_name = normalized.get("client_name")
    if isinstance(client_name, str):
        normalized["client_name"] = parse_client_name(client_name)
    return normalized
