"""Build deterministic, bounded OMS queries for one Airflow task attempt."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

from workspaces.data_engineering.agents.production_support.models import Region

OMS_TABLE = "DI_Scheduling_CL"
UTC = ZoneInfo("UTC")


class OmsQueryParameterError(ValueError):
    """Raised when an OMS query cannot be built safely."""

    @classmethod
    def timezone_required(cls) -> OmsQueryParameterError:
        """Return an error for a naive start timestamp."""
        return cls("start_at must be timezone-aware")

    @classmethod
    def positive_try_required(cls) -> OmsQueryParameterError:
        """Return an error for a non-positive attempt."""
        return cls("try_number_d must be positive")

    @classmethod
    def empty_identity(cls, label: str) -> OmsQueryParameterError:
        """Return an error for an empty identity field."""
        return cls(f"{label} must not be empty")

    @classmethod
    def unsupported_table(cls) -> OmsQueryParameterError:
        """Return an error for a broad or unsupported table."""
        return cls(f"table must be {OMS_TABLE}")


@dataclass(frozen=True, slots=True)
class OmsJobQueryParameters:
    """Exact job identity and date used for one OMS lookup."""

    region: Region
    client_id_g: str
    run_id_s: str
    task_id_s: str
    try_number_d: int
    start_at: datetime
    table: str = OMS_TABLE

    def __post_init__(self) -> None:
        """Reject incomplete or unsafe query parameters."""
        if self.start_at.tzinfo is None:
            raise OmsQueryParameterError.timezone_required()
        if self.try_number_d < 1:
            raise OmsQueryParameterError.positive_try_required()
        for value, label in (
            (self.client_id_g, "client_id_g"),
            (self.run_id_s, "run_id_s"),
            (self.task_id_s, "task_id_s"),
        ):
            if not value.strip():
                raise OmsQueryParameterError.empty_identity(label)
        if self.table != OMS_TABLE:
            raise OmsQueryParameterError.unsupported_table()


@dataclass(frozen=True, slots=True)
class OmsJobQuery:
    """Executable OMS query plus its routing and audit metadata."""

    workspace_name: str
    table: str
    window_start: datetime
    window_end: datetime
    kql: str


def build_oms_job_query(parameters: OmsJobQueryParameters) -> OmsJobQuery:
    """Build one exact OMS query bounded to the task's UTC calendar day."""
    task_day = parameters.start_at.astimezone(UTC).date()
    window_start = datetime.combine(task_day, time.min, tzinfo=UTC)
    window_end = datetime.combine(task_day, time.max, tzinfo=UTC)
    kql = "\n".join(
        (
            parameters.table,
            (
                "| where TimeGenerated between "
                f"(datetime({window_start.isoformat()}) .. "
                f"datetime({window_end.isoformat()}))"
            ),
            f"| where client_id_g == {_quote(parameters.client_id_g)}",
            f"| where run_id_s == {_quote(parameters.run_id_s)}",
            f"| where task_id_s == {_quote(parameters.task_id_s)}",
            f"| where try_number_d == {parameters.try_number_d}",
            "| project TimeGenerated, message_s, level_s, pod_name_s",
            "| order by TimeGenerated asc",
        )
    )
    return OmsJobQuery(
        workspace_name=_workspace_for(parameters.region),
        table=parameters.table,
        window_start=window_start,
        window_end=window_end,
        kql=kql,
    )


def _workspace_for(region: Region) -> str:
    return {
        Region.US_01: "pl-oms-us-primary",
        Region.CA_02: "pl-oms-ca-primary",
    }[region]


def _quote(value: str) -> str:
    return json.dumps(value)
