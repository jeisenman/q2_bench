"""Validated findings shared by production-support reporters."""

from __future__ import annotations

from dataclasses import dataclass, field

from domain import AgentResult
from workspaces.data_engineering.workflows.prod_support.cluster_health import (
    RegionalClusterHealth,
)
from workspaces.data_engineering.workflows.prod_support.models import (
    AirflowFailure,
    FailureDiagnosis,
    Region,
)
from workspaces.data_engineering.workflows.prod_support.reporting_config import (
    ProdSupportReportConfig,
)
from workspaces.data_engineering.workflows.prod_support.reporting_validation import (
    ReportContractError,
    validate_report_inputs,
)


@dataclass(frozen=True, slots=True)
class ReportFindings:
    """Immutable, validated evidence supplied to audience reporters."""

    failures: tuple[AirflowFailure, ...]
    diagnoses: tuple[FailureDiagnosis, ...]
    resource_discovery_results: tuple[AgentResult, ...] = ()
    config: ProdSupportReportConfig = field(default_factory=ProdSupportReportConfig)
    cluster_health: tuple[RegionalClusterHealth, ...] = ()
    regions: tuple[Region, ...] = (Region.US_01, Region.CA_02)

    def __post_init__(self) -> None:
        """Fail closed when findings cannot produce a consistent report."""
        if not self.regions:
            raise ReportContractError.empty_regions()
        if len(set(self.regions)) != len(self.regions):
            raise ReportContractError.duplicate_regions()
        validate_report_inputs(
            self.failures,
            self.diagnoses,
            self.cluster_health,
        )
