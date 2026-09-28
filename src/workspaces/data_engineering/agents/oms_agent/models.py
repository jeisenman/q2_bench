"""Immutable OMS connection, query, and log contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class OmsEnvironment(StrEnum):
    """Supported deployment environments."""

    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPMENT = "development"


class OmsRegion(StrEnum):
    """Supported OMS regions."""

    US = "us"
    CA = "ca"


@dataclass(frozen=True, slots=True)
class OmsWorkspace:
    """Identify one Azure Log Analytics workspace."""

    name: str
    workspace_id: str
    subscription_id: str


_PRODUCTION_SUBSCRIPTION = "71aa0ec0-8411-43a2-9908-ddd2add764eb"
_PREPROD_SUBSCRIPTION = "cde221ff-e7f4-4d39-be20-6f9d532cab60"
_WORKSPACES = MappingProxyType(
    {
        (OmsEnvironment.PRODUCTION, OmsRegion.US): OmsWorkspace(
            name="pl-oms-us-primary",
            workspace_id="6220c6e1-57a3-49c2-901c-bb5e5106f2b0",
            subscription_id=_PRODUCTION_SUBSCRIPTION,
        ),
        (OmsEnvironment.PRODUCTION, OmsRegion.CA): OmsWorkspace(
            name="pl-oms-ca-primary",
            workspace_id="2fc9684b-5d16-42f0-ab99-9dc044e4ea73",
            subscription_id=_PRODUCTION_SUBSCRIPTION,
        ),
        (OmsEnvironment.STAGING, OmsRegion.US): OmsWorkspace(
            name="pl-oms-preprod-primary",
            workspace_id="10983741-32db-4a0f-8607-61558f19b657",
            subscription_id=_PREPROD_SUBSCRIPTION,
        ),
        (OmsEnvironment.DEVELOPMENT, OmsRegion.US): OmsWorkspace(
            name="pl-oms-preprod-primary",
            workspace_id="10983741-32db-4a0f-8607-61558f19b657",
            subscription_id=_PREPROD_SUBSCRIPTION,
        ),
    }
)


class OmsWorkspaceError(ValueError):
    """Raised when an environment and region have no configured workspace."""

    @classmethod
    def unsupported(
        cls, environment: OmsEnvironment, region: OmsRegion
    ) -> OmsWorkspaceError:
        """Create an actionable unsupported-route error."""
        return cls(
            f"no OMS workspace is configured for "
            f"environment={environment.value!r}, region={region.value!r}"
        )


def resolve_workspace(
    environment: OmsEnvironment,
    region: OmsRegion,
) -> OmsWorkspace:
    """Return the hardcoded workspace for an explicit environment and region."""
    try:
        return _WORKSPACES[(environment, region)]
    except KeyError as error:
        raise OmsWorkspaceError.unsupported(environment, region) from error


@dataclass(frozen=True, slots=True)
class OmsQuery:
    """Represent one bounded KQL query."""

    kql: str
    timespan: str

    def __post_init__(self) -> None:
        """Reject blank or unbounded query inputs."""
        if not self.kql.strip():
            message = "kql must not be empty"
            raise ValueError(message)
        if not self.timespan.strip():
            message = "timespan must not be empty"
            raise ValueError(message)


@dataclass(frozen=True, slots=True)
class OmsQueryResult:
    """Return provider-neutral tabular query data."""

    columns: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True, slots=True)
class OmsLogRecord:
    """Represent one custom OMS log entry."""

    log_type: str
    fields: Mapping[str, object]

    def __post_init__(self) -> None:
        """Validate the Data Collector API log type and payload."""
        if not self.log_type.strip():
            message = "log_type must not be empty"
            raise ValueError(message)
        if not self.log_type.replace("_", "").isalnum():
            message = "log_type must contain only letters, numbers, or underscores"
            raise ValueError(message)
        if not self.fields:
            message = "fields must not be empty"
            raise ValueError(message)
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))
