"""Render evidence-derived regional cluster health."""

from __future__ import annotations

from workspaces.data_engineering.agents.prod_support.cluster_health import (
    RegionalClusterHealth,
)
from workspaces.data_engineering.agents.prod_support.models import Region

PAIR_SIZE = 2


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
        details.append(f"{observation.restart_count} pod restarts")
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


def data_internal_health_line(observation: RegionalClusterHealth) -> str:
    """Render one unhealthy regional summary and observed symptoms."""
    label = "US" if observation.region is Region.US_01 else "CA"
    symptoms = observation.symptoms or _derived_symptoms(observation)
    joined = _join_terms((*symptoms, *observation.warnings))
    return f"  - {label} cluster is unhealthy; {joined} appear"


def _derived_symptoms(observation: RegionalClusterHealth) -> tuple[str, ...]:
    symptoms: list[str] = []
    if observation.application_healthy is False:
        symptoms.append("application health checks are failing")
    if observation.pods_healthy is False:
        symptoms.append("pods are unready")
    if observation.dags_parsing_healthy is False:
        symptoms.append("DAG parsing is unhealthy")
    if observation.active_dag_count == 0:
        symptoms.append("zero active DAGs")
    return tuple(symptoms) or ("primary cluster health checks are failing",)


def _join_terms(values: tuple[str, ...]) -> str:
    if len(values) < PAIR_SIZE:
        return "".join(values)
    if len(values) == PAIR_SIZE:
        return " and ".join(values)
    return f"{', '.join(values[:-1])}, and {values[-1]}"
