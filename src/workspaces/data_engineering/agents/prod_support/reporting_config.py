"""Typed production-support audience configuration."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from workspaces.data_engineering.agents.prod_support.models import AirflowFailure


class DataInternalOmissionGroup(StrEnum):
    """Supported groups that can be omitted from Data Internal."""

    D2P = "d2p"
    MI3 = "mi3"
    SUBSCRIBER = "subscriber"
    MAINTENANCE = "maintenance"
    BACKFILL = "backfill"
    CMM = "cmm"


DEFAULT_DATA_INTERNAL_OMISSIONS = (
    DataInternalOmissionGroup.D2P,
    DataInternalOmissionGroup.MI3,
    DataInternalOmissionGroup.SUBSCRIBER,
    DataInternalOmissionGroup.MAINTENANCE,
    DataInternalOmissionGroup.BACKFILL,
    DataInternalOmissionGroup.CMM,
)

_OMISSION_PATTERNS = {
    DataInternalOmissionGroup.D2P: ("delivery_to_promise",),
    DataInternalOmissionGroup.MI3: ("market_insights_3", "mi_3"),
    DataInternalOmissionGroup.SUBSCRIBER: (
        "check_for_subscriber_client_errors",
        "subscriber",
    ),
    DataInternalOmissionGroup.MAINTENANCE: ("log_cleanup", "expire_logs"),
    DataInternalOmissionGroup.BACKFILL: ("backfill",),
    DataInternalOmissionGroup.CMM: (
        "credit_migration_matrix",
        "credit-migration-matrix",
        "cmm",
    ),
}


@dataclass(frozen=True, slots=True)
class ProdSupportReportConfig:
    """Control audience filtering without changing investigation coverage."""

    data_internal_omissions: tuple[DataInternalOmissionGroup, ...] = (
        DEFAULT_DATA_INTERNAL_OMISSIONS
    )

    @classmethod
    def from_omission_values(
        cls,
        values: Sequence[str] | None,
    ) -> ProdSupportReportConfig:
        """Build configuration from MCP-safe string values."""
        if values is None:
            return cls()
        parsed: list[DataInternalOmissionGroup] = []
        for value in values:
            if not isinstance(value, str) or not value.strip():
                message = "data_internal_omissions must contain non-empty strings"
                raise ValueError(message)
            try:
                group = DataInternalOmissionGroup(value.strip().lower())
            except ValueError as error:
                supported = ", ".join(item.value for item in DataInternalOmissionGroup)
                message = (
                    f"unsupported Data Internal omission {value!r}; "
                    f"expected one of: {supported}"
                )
                raise ValueError(message) from error
            if group in parsed:
                message = f"duplicate Data Internal omission: {group.value}"
                raise ValueError(message)
            parsed.append(group)
        return cls(tuple(parsed))

    def omits(self, failure: AirflowFailure) -> bool:
        """Return whether a failure is hidden from Data Internal and follow-ups."""
        identity = f"{failure.dag_id} {failure.task_id}".lower()
        return any(
            pattern in identity
            for group in self.data_internal_omissions
            for pattern in _OMISSION_PATTERNS[group]
        )
