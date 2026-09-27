"""Typed regional cluster-health observations and derived status."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from workspaces.data_engineering.agents.prod_support.models import Region


class ClusterHealthState(StrEnum):
    """Evidence-derived overall health for one regional cluster."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ClusterHealthValueError(ValueError):
    """Raised when a cluster-health observation is invalid."""

    @classmethod
    def timezone_required(cls) -> ClusterHealthValueError:
        """Return an error for a naive observation timestamp."""
        return cls("cluster-health observed_at must be timezone-aware")

    @classmethod
    def negative_dag_count(cls) -> ClusterHealthValueError:
        """Return an error for a negative active DAG count."""
        return cls("active_dag_count must not be negative")

    @classmethod
    def negative_restart_count(cls) -> ClusterHealthValueError:
        """Return an error for a negative restart count."""
        return cls("restart_count must not be negative")

    @classmethod
    def empty_keda_status(cls) -> ClusterHealthValueError:
        """Return an error for an empty KEDA status."""
        return cls("keda_status must not be empty")

    @classmethod
    def empty_observation(cls) -> ClusterHealthValueError:
        """Return an error for an empty symptom or warning."""
        return cls("cluster-health symptoms and warnings must not be empty")


@dataclass(frozen=True, slots=True)
class RegionalClusterHealth:
    """Read-only health evidence for one Airflow region."""

    region: Region
    observed_at: datetime | None = None
    application_healthy: bool | None = None
    pods_healthy: bool | None = None
    dags_parsing_healthy: bool | None = None
    active_dag_count: int | None = None
    restart_count: int | None = None
    keda_status: str = "unknown"
    symptoms: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject contradictory or incomplete boundary values."""
        if self.observed_at is not None and self.observed_at.tzinfo is None:
            raise ClusterHealthValueError.timezone_required()
        if self.active_dag_count is not None and self.active_dag_count < 0:
            raise ClusterHealthValueError.negative_dag_count()
        if self.restart_count is not None and self.restart_count < 0:
            raise ClusterHealthValueError.negative_restart_count()
        if not self.keda_status.strip():
            raise ClusterHealthValueError.empty_keda_status()
        if any(not item.strip() for item in (*self.symptoms, *self.warnings)):
            raise ClusterHealthValueError.empty_observation()

    @property
    def state(self) -> ClusterHealthState:
        """Derive health from primary checks without promoting warnings."""
        primary = (
            self.application_healthy,
            self.pods_healthy,
            self.dags_parsing_healthy,
        )
        if False in primary or self.active_dag_count == 0:
            return ClusterHealthState.UNHEALTHY
        known = tuple(value for value in primary if value is not None)
        if (
            known
            and all(value is True for value in known)
            and (self.active_dag_count is None or self.active_dag_count > 0)
        ):
            return ClusterHealthState.HEALTHY
        return ClusterHealthState.UNKNOWN

    @classmethod
    def unavailable(cls, region: Region) -> RegionalClusterHealth:
        """Return an explicit evidence-gap observation."""
        return cls(
            region=region,
            symptoms=("cluster health evidence is unavailable",),
        )
