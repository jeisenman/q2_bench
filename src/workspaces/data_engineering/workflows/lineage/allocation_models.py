"""Immutable resource-allocation contracts for lineage transformations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self


@dataclass(frozen=True, slots=True)
class ResourceAllocation:
    """Compute backend and explicit resource settings for one job."""

    compute: str
    container_resources: tuple[tuple[str, str], ...] = ()
    spark_configuration: tuple[tuple[str, str], ...] = ()
    spark_variables: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Serialize one resolved resource allocation."""
        return {
            "compute": self.compute,
            "containerResources": dict(self.container_resources),
            "sparkConfiguration": dict(self.spark_configuration),
            "sparkVariables": dict(self.spark_variables),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        """Deserialize one resource allocation."""
        return cls(
            compute=str(value["compute"]),
            container_resources=_pairs(value.get("containerResources")),
            spark_configuration=_pairs(value.get("sparkConfiguration")),
            spark_variables=_pairs(value.get("sparkVariables")),
        )


@dataclass(frozen=True, slots=True)
class ClientAllocationOverride:
    """A client receiving resources different from the standard allocation."""

    client_id: str
    client_name: str | None
    resource_size: str
    allocation: ResourceAllocation

    def to_dict(self) -> dict[str, object]:
        """Serialize a client-specific allocation."""
        return {
            "clientId": self.client_id,
            "clientName": self.client_name,
            "resourceSize": self.resource_size,
            "allocation": self.allocation.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        """Deserialize a client-specific allocation."""
        return cls(
            client_id=str(value["clientId"]),
            client_name=(
                str(value["clientName"])
                if value.get("clientName") is not None
                else None
            ),
            resource_size=str(value["resourceSize"]),
            allocation=ResourceAllocation.from_dict(_mapping(value["allocation"])),
        )


@dataclass(frozen=True, slots=True)
class JobAllocation:
    """Standard allocation and larger client-specific variants."""

    standard: ResourceAllocation
    larger_clients: tuple[ClientAllocationOverride, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Serialize a job allocation policy."""
        return {
            "standard": self.standard.to_dict(),
            "largerClients": [item.to_dict() for item in self.larger_clients],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        """Deserialize a job allocation policy."""
        raw_clients = value.get("largerClients", ())
        clients = raw_clients if isinstance(raw_clients, list | tuple) else ()
        return cls(
            standard=ResourceAllocation.from_dict(_mapping(value["standard"])),
            larger_clients=tuple(
                ClientAllocationOverride.from_dict(_mapping(item)) for item in clients
            ),
        )


def _pairs(value: object) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(_mapping(value).items()))


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}
