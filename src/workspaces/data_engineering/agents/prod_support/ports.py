"""Production and replay data interfaces for production support."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from domain import AgentRequest, AgentResult
from workspaces.data_engineering.agents.prod_support.cluster_health import (
    RegionalClusterHealth,
)
from workspaces.data_engineering.agents.prod_support.models import (
    AirflowFailure,
    PriorTaskLog,
    Region,
)
from workspaces.data_engineering.agents.prod_support.oms import (
    OmsJobQueryParameters,
)
from workspaces.data_engineering.agents.prod_support.workloads import (
    AirflowTaskMetadata,
)


class TaskLogUnavailableError(RuntimeError):
    """Raised when Airflow has a task instance but no retrievable log."""

    def __init__(self, failure_id: str, status_code: int) -> None:
        """Identify the unavailable task log without exposing credentials."""
        self.failure_id = failure_id
        self.status_code = status_code
        super().__init__(
            f"Airflow task log unavailable for {failure_id}: HTTP {status_code}"
        )


class OmsEvidenceUnavailableError(RuntimeError):
    """Raised when an exact OMS query cannot return evidence."""

    @classmethod
    def not_configured(cls) -> OmsEvidenceUnavailableError:
        """Return an error for a missing OMS evidence source."""
        return cls("OMS source is not configured")


class AirflowFailureSource(Protocol):
    """Read Airflow failure metadata and exact task logs."""

    async def discover_failures(self, since: datetime) -> tuple[AirflowFailure, ...]:
        """Return candidate failures, including enough history to test filtering."""
        ...

    async def fetch_log(self, failure: AirflowFailure) -> str:
        """Return the exact task-instance log for a failure."""
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


class OmsJobEvidenceSource(Protocol):
    """Read one exact OMS job identity."""

    async def query_job(self, parameters: OmsJobQueryParameters) -> str:
        """Return bounded log evidence for one exact Spark attempt."""
        ...


class ClusterHealthSource(Protocol):
    """Read current regional Airflow and KEDA health evidence."""

    async def inspect_health(self, region: Region) -> RegionalClusterHealth:
        """Return one evidence-derived regional observation."""
        ...


class ResourceDiscoveryInvoker(Protocol):
    """Invoke the read-only Resource Discovery agent."""

    async def run(self, request: AgentRequest) -> AgentResult:
        """Resolve non-secret resource metadata for one client identifier."""
        ...
