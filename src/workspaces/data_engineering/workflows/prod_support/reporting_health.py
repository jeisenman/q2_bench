"""Render evidence-derived regional cluster health."""

from __future__ import annotations

from workspaces.data_engineering.workflows.prod_support.cluster_health import (
    RegionalClusterHealth,
)
from workspaces.data_engineering.workflows.prod_support.models import Region


def health_by_region(
    observations: tuple[RegionalClusterHealth, ...],
    regions: tuple[Region, ...] = (Region.US_01, Region.CA_02),
) -> dict[Region, RegionalClusterHealth]:
    """Return complete regional health, filling explicit evidence gaps."""
    indexed = {observation.region: observation for observation in observations}
    return {
        region: indexed.get(region, RegionalClusterHealth.unavailable(region))
        for region in regions
    }


def developer_health_line(observation: RegionalClusterHealth) -> str:
    """Render one compact health line without contradicting warnings."""
    label = "US" if observation.region is Region.US_01 else "CA"
    details: list[str] = []
    if observation.observed_at is not None:
        details.append(f"observed {observation.observed_at.isoformat()}")
    if observation.active_dag_count is not None:
        details.append(f"{observation.active_dag_count} active DAGs")
    if observation.restart_count is not None:
        if (
            observation.restart_window_start is not None
            and observation.restart_window_end is not None
        ):
            details.append(
                f"{observation.restart_count} observed container restarts from "
                f"{observation.restart_window_start.isoformat()} through "
                f"{observation.restart_window_end.isoformat()}"
            )
        else:
            details.append(f"{observation.restart_count} pod restarts")
    if observation.cumulative_restart_count is not None:
        details.append(
            f"{observation.cumulative_restart_count} cumulative container restarts"
        )
    details.extend(observation.symptoms)
    details.extend(observation.warnings)
    if observation.keda_status != "unknown":
        details.append(f"KEDA {observation.keda_status.replace('_', ' ')}")
    suffix = f"; {'; '.join(dict.fromkeys(details))}" if details else ""
    return f"  - {label} Cluster Health: {observation.state.value}{suffix}"


def dag_parsing_line(
    observations: dict[Region, RegionalClusterHealth],
) -> str | None:
    """Render active DAG counts only when both parsing checks succeeded."""
    us = observations[Region.US_01]
    ca = observations[Region.CA_02]
    if (
        us.dags_parsing_healthy is not True
        or ca.dags_parsing_healthy is not True
        or us.active_dag_count is None
        or ca.active_dag_count is None
    ):
        return None
    return (
        "  - DAGs parsing properly: "
        f"{us.active_dag_count} DAGs exist in US, "
        f"{ca.active_dag_count} DAGs exist in CA"
    )
