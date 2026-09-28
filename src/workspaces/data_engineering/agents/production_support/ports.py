"""Production and replay data interfaces for production support."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from domain import AgentRequest, AgentResult
from workspaces.data_engineering.agents.oms_agent import (
    OmsEvidenceUnavailableError,
    OmsJobEvidenceSource,
)
from workspaces.data_engineering.agents.production_support.cluster_health import (
    RegionalClusterHealth,
)
from workspaces.data_engineering.agents.production_support.models import (
    AirflowFailure,
    PriorTaskLog,
    Region,
)
from workspaces.data_engineering.agents.production_support.retry_models import (
    RetryBatch,
    RetryTaskReference,
)
from workspaces.data_engineering.agents.production_support.workloads import (
    AirflowTaskMetadata,
)

if TYPE_CHECKING:
    from workspaces.data_engineering.agents.production_support.reporting_config import (
        ProdSupportReportConfig,
    )

__all__ = [
    "AirflowFailureSource",
    "AirflowRetrySource",
    "AirflowSuccessSource",
    "AirflowTaskMetadataSource",
    "ClusterHealthSource",
    "DagAirflowFailureSource",
    "OmissionStore",
    "OmsEvidenceUnavailableError",
    "OmsJobEvidenceSource",
    "PriorTaskLogSource",
    "RegionalAirflowFailureSource",
    "ResourceDiscoveryInvoker",
    "TaskLogUnavailableError",
]


class TaskLogUnavailableError(RuntimeError):
    """Raised when Airflow has a task instance but no retrievable log."""

    def __init__(self, failure_id: str, status_code: int) -> None:
        """Identify the unavailable task log without exposing credentials."""
        self.failure_id = failure_id
        self.status_code = status_code
        super().__init__(
            f"Airflow task log unavailable for {failure_id}: HTTP {status_code}"
        )


class AirflowFailureSource(Protocol):
    """Read Airflow failure metadata and exact task logs."""

    async def discover_failures(self, since: datetime) -> tuple[AirflowFailure, ...]:
        """Return candidate failures, including enough history to test filtering."""
        ...

    async def fetch_log(self, failure: AirflowFailure) -> str:
        """Return the exact task-instance log for a failure."""
        ...


@runtime_checkable
class DagAirflowFailureSource(Protocol):
    """Read failures for one exact Airflow DAG."""

    async def discover_dag_failures(
        self,
        dag_id: str,
        since: datetime,
    ) -> tuple[AirflowFailure, ...]:
        """Return failures for the exact DAG ending at or after the cutoff."""
        ...


@runtime_checkable
class AirflowSuccessSource(Protocol):
    """Verify recovery for the same DAG and task in a bounded window."""

    async def has_success_within(
        self,
        failure: AirflowFailure,
        start_at: datetime,
        end_at: datetime,
    ) -> bool:
        """Return whether the same DAG/task succeeded inside the window."""
        ...


class OmissionStore(Protocol):
    """Persist operator-configured Data Internal omission groups."""

    def load(self) -> ProdSupportReportConfig:
        """Return validated omission configuration."""
        ...

    def save(self, values: Sequence[str]) -> ProdSupportReportConfig:
        """Validate and persist omission values."""
        ...


@runtime_checkable
class RegionalAirflowFailureSource(Protocol):
    """Read Airflow failures from one explicitly selected region."""

    async def discover_region_failures(
        self,
        region: Region,
        since: datetime,
    ) -> tuple[AirflowFailure, ...]:
        """Return failures for one production region."""
        ...


class AirflowTaskMetadataSource(Protocol):
    """Read task operator metadata used for workload routing."""

    async def fetch_task_metadata(
        self,
        failure: AirflowFailure,
    ) -> AirflowTaskMetadata:
        """Return exact metadata for one failed task."""
        ...


class PriorTaskLogSource(Protocol):
    """Read bounded prior logs for the exact same DAG and task."""

    async def fetch_prior_logs(
        self,
        failure: AirflowFailure,
        limit: int,
    ) -> tuple[PriorTaskLog, ...]:
        """Return attempts before the supplied failure, newest first."""
        ...


class ClusterHealthSource(Protocol):
    """Read current regional Airflow and KEDA health evidence."""

    async def inspect_health(
        self,
        region: Region,
        restart_window_start: datetime,
        restart_window_end: datetime,
    ) -> RegionalClusterHealth:
        """Return one evidence-derived regional observation."""
        ...


class AirflowRetrySource(Protocol):
    """Dry-run and execute exact regional Airflow task retries."""

    async def plan_retry(
        self,
        batch: RetryBatch,
    ) -> tuple[RetryTaskReference, ...]:
        """Return Airflow's dry-run selection for one exact DAG run."""
        ...

    async def execute_retry(
        self,
        batch: RetryBatch,
        approval_id: str,
    ) -> tuple[RetryTaskReference, ...]:
        """Clear the exact approved tasks and return their current states."""
        ...


class ResourceDiscoveryInvoker(Protocol):
    """Invoke the read-only Resource Discovery agent."""

    async def run(self, request: AgentRequest) -> AgentResult:
        """Resolve non-secret resource metadata for one client identifier."""
        ...
