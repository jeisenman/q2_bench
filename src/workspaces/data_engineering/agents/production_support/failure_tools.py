"""Deterministic failure-discovery and exact-log tools."""

from datetime import datetime

from workspaces.data_engineering.agents.production_support.airflow_checker import (
    AirflowChecker,
)
from workspaces.data_engineering.agents.production_support.models import (
    AirflowFailure,
    Region,
)
from workspaces.data_engineering.agents.production_support.ports import (
    AirflowFailureSource,
    DagAirflowFailureSource,
)


class FailureDiscoveryTool:
    """Query bounded Airflow failures without inspecting their logs."""

    def __init__(self, source: AirflowFailureSource) -> None:
        """Initialize with one read-only Airflow source."""
        self._source = source
        self._checker = AirflowChecker(source)

    async def discover(
        self,
        failed_since: datetime,
        failed_before: datetime,
        regions: tuple[Region, ...],
    ) -> tuple[AirflowFailure, ...]:
        """Return bounded failures for the selected regions."""
        return await self._checker.check(
            failed_since,
            failed_before,
            regions=regions,
        )

    async def discover_client(
        self,
        dag_id: str,
        failed_since: datetime,
    ) -> tuple[AirflowFailure, ...]:
        """Return failures for one exact client DAG."""
        if not isinstance(self._source, DagAirflowFailureSource):
            message = "client investigation requires exact DAG failure discovery"
            raise TypeError(message)
        return await self._source.discover_dag_failures(dag_id, failed_since)


class ExactLogTool:
    """Fetch one exact Airflow task-attempt log."""

    def __init__(self, source: AirflowFailureSource) -> None:
        """Initialize with one read-only Airflow source."""
        self._source = source

    async def fetch(self, failure: AirflowFailure) -> str:
        """Return the exact task-attempt log."""
        return await self._source.fetch_log(failure)
