"""Fail-closed validation for production-support report inputs."""

from __future__ import annotations

from workspaces.data_engineering.agents.prod_support.cluster_health import (
    RegionalClusterHealth,
)
from workspaces.data_engineering.agents.prod_support.models import (
    AirflowFailure,
    FailureDiagnosis,
)


class ReportContractError(ValueError):
    """Raised when findings cannot produce a consistent report."""

    @classmethod
    def duplicate_failures(cls) -> ReportContractError:
        """Return an error for duplicate task-instance identities."""
        return cls("duplicate Airflow failure identities")

    @classmethod
    def duplicate_diagnoses(cls) -> ReportContractError:
        """Return an error for duplicate diagnoses."""
        return cls("duplicate failure diagnoses")

    @classmethod
    def incomplete_diagnoses(cls) -> ReportContractError:
        """Return an error for a diagnosis/failure mismatch."""
        return cls("every Airflow failure must have exactly one matching diagnosis")

    @classmethod
    def duplicate_health(cls) -> ReportContractError:
        """Return an error for duplicate regional health."""
        return cls("duplicate regional cluster-health observations")

    @classmethod
    def empty_regions(cls) -> ReportContractError:
        """Return an error for an empty reporting scope."""
        return cls("report findings must include at least one region")

    @classmethod
    def duplicate_regions(cls) -> ReportContractError:
        """Return an error for duplicate reporting regions."""
        return cls("report findings contain duplicate regions")


def validate_report_inputs(
    failures: tuple[AirflowFailure, ...],
    diagnoses: tuple[FailureDiagnosis, ...],
    cluster_health: tuple[RegionalClusterHealth, ...],
) -> None:
    """Require unique findings, complete diagnoses, and regional health."""
    failure_ids = tuple(failure.failure_id for failure in failures)
    diagnosis_ids = tuple(diagnosis.failure_id for diagnosis in diagnoses)
    if len(set(failure_ids)) != len(failure_ids):
        raise ReportContractError.duplicate_failures()
    if len(set(diagnosis_ids)) != len(diagnosis_ids):
        raise ReportContractError.duplicate_diagnoses()
    if set(failure_ids) != set(diagnosis_ids):
        raise ReportContractError.incomplete_diagnoses()
    health_regions = tuple(observation.region for observation in cluster_health)
    if len(set(health_regions)) != len(health_regions):
        raise ReportContractError.duplicate_health()
