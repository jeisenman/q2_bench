"""Production and replay data interfaces for production support."""

from datetime import datetime
from typing import Protocol

from workspaces.data_engineering.agents.prod_support.models import AirflowFailure


class AirflowFailureSource(Protocol):
    """Read Airflow failure metadata and exact task logs."""

    async def discover_failures(self, since: datetime) -> tuple[AirflowFailure, ...]:
        """Return candidate failures, including enough history to test filtering."""
        ...

    async def fetch_log(self, failure: AirflowFailure) -> str:
        """Return the exact task-instance log for a failure."""
        ...
