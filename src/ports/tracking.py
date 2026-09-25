"""Experiment tracking port."""

from typing import Protocol

from domain import AgentRequest, AgentResult, BenchmarkIdentity
from domain.models import Attributes


class TrackingPort(Protocol):
    """Track agent and benchmark activity."""

    async def start_run(
        self,
        benchmark: BenchmarkIdentity,
        request: AgentRequest,
    ) -> str:
        """Start a run and return its provider-neutral identifier."""
        ...

    async def log_result(self, run_id: str, result: AgentResult) -> None:
        """Log the result for a run."""
        ...

    async def annotate_failure(
        self,
        run_id: str,
        category: str,
        details: str,
        *,
        attributes: Attributes = (),
    ) -> None:
        """Attach a structured failure annotation."""
        ...
