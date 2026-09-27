"""Typed production-support audience configuration."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from workspaces.data_engineering.agents.production_support.models import AirflowFailure


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
    DataInternalOmissionGroup.D2P: ("delivery_to_promise", "d2p"),
    DataInternalOmissionGroup.MI3: ("market_insights_3", "mi_3", "mi3"),
    DataInternalOmissionGroup.SUBSCRIBER: (
        "check_for_subscriber_client_errors",
        "subscriber",
    ),
    DataInternalOmissionGroup.MAINTENANCE: (
        "log_cleanup",
        "expire_logs",
        "expire-logs",
    ),
    DataInternalOmissionGroup.BACKFILL: ("backfill",),
    DataInternalOmissionGroup.CMM: (
        "credit_migration_matrix",
        "credit-migration-matrix",
        "cmm",
    ),
}
_OMISSION_CODES = {
    DataInternalOmissionGroup.D2P: "D2P",
    DataInternalOmissionGroup.MI3: "MI3",
    DataInternalOmissionGroup.SUBSCRIBER: "Subscriber",
    DataInternalOmissionGroup.MAINTENANCE: "log_cleanup",
    DataInternalOmissionGroup.BACKFILL: "Backfill",
    DataInternalOmissionGroup.CMM: "CMM",
}
_DATA_INTERNAL_SHORTHAND_GROUPS = (
    DataInternalOmissionGroup.MI3,
    DataInternalOmissionGroup.D2P,
)
OMISSION_SETTINGS_URI = "agent://prod-support/omissions"


@dataclass(frozen=True, slots=True)
class ProdSupportReportConfig:
    """Control audience filtering after bounded recovery verification."""

    data_internal_omissions: tuple[DataInternalOmissionGroup, ...] = (
        DEFAULT_DATA_INTERNAL_OMISSIONS
    )
    verified_omission_failure_ids: frozenset[str] | None = None

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

    def with_verified_omissions(
        self,
        failure_ids: Sequence[str],
    ) -> ProdSupportReportConfig:
        """Return configuration limited to verified recovered failures."""
        return ProdSupportReportConfig(
            self.data_internal_omissions,
            frozenset(failure_ids),
        )

    def omits(self, failure: AirflowFailure) -> bool:
        """Return whether a verified recovery collapses to an omission code."""
        return self.omission_group(failure) is not None

    def omission_group(
        self,
        failure: AirflowFailure,
    ) -> DataInternalOmissionGroup | None:
        """Return the configured compact-code group for a failure."""
        if (
            self.verified_omission_failure_ids is not None
            and failure.failure_id not in self.verified_omission_failure_ids
        ):
            return None
        return self.configured_omission_group(failure)

    def configured_omission_group(
        self,
        failure: AirflowFailure,
    ) -> DataInternalOmissionGroup | None:
        """Return the configured group before recovery verification."""
        identity = f"{failure.dag_id} {failure.task_id}".lower()
        return next(
            (
                group
                for group in self.data_internal_omissions
                if any(pattern in identity for pattern in _OMISSION_PATTERNS[group])
            ),
            None,
        )

    def omission_codes(
        self,
        failures: tuple[AirflowFailure, ...],
    ) -> tuple[str, ...]:
        """Return configured codes represented by regional failures."""
        present = {
            group
            for failure in failures
            if (group := self.omission_group(failure)) is not None
        }
        return tuple(
            _OMISSION_CODES[group]
            for group in self.data_internal_omissions
            if group in present
        )

    def shorthand_codes(
        self,
        failures: tuple[AirflowFailure, ...],
    ) -> tuple[str, ...]:
        """Return represented MI3 and D2P shorthand in canonical order."""
        present = {
            group
            for failure in failures
            if (group := self.configured_omission_group(failure)) is not None
        }
        return tuple(
            _OMISSION_CODES[group]
            for group in _DATA_INTERNAL_SHORTHAND_GROUPS
            if group in present
        )

    def linked_omission_codes(self) -> tuple[str, ...]:
        """Return configured omission codes linked to their settings interface."""
        return tuple(
            f"[{_OMISSION_CODES[group]}]({OMISSION_SETTINGS_URI}#{group.value})"
            for group in self.data_internal_omissions
        )

    def skips_airflow_triage(self, failure: AirflowFailure) -> bool:
        """Return false because omission candidates still require exact logs."""
        del failure
        return False


def update_omission_values(
    current: Sequence[str],
    direction: str,
) -> tuple[str, ...]:
    """Apply an explicit conversational add/remove omission request."""
    lowered = direction.casefold()
    add = "add" in lowered
    remove = "remove" in lowered or "delete" in lowered
    if add == remove:
        message = "omission direction must say exactly one of add or remove"
        raise ValueError(message)
    requested = tuple(
        group
        for group in DataInternalOmissionGroup
        if group.value in lowered or _OMISSION_CODES[group].casefold() in lowered
    )
    if not requested:
        supported = ", ".join(item.value for item in DataInternalOmissionGroup)
        message = f"omission direction must name one of: {supported}"
        raise ValueError(message)
    parsed = list(
        ProdSupportReportConfig.from_omission_values(current).data_internal_omissions
    )
    for group in requested:
        if add and group not in parsed:
            parsed.append(group)
        if remove and group in parsed:
            parsed.remove(group)
    return tuple(item.value for item in parsed)
