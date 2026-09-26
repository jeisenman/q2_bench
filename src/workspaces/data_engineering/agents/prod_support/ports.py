"""Production and replay data interfaces for production support."""

from datetime import datetime
from typing import Protocol

from workspaces.data_engineering.agents.prod_support.models import AirflowFailure
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
