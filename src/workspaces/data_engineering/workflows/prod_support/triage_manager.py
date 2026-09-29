"""Batch production-failure triage with short-circuiting evidence retrieval."""

from __future__ import annotations

import asyncio

from observability import traced_operation
from workspaces.data_engineering.workflows.prod_support.investigation import (
    FailureInvestigator,
)
from workspaces.data_engineering.workflows.prod_support.models import (
    AirflowFailure,
    FailureDiagnosis,
)


class TriageManager:
    """Triage one complete failure batch without spawning per-failure agents."""

    def __init__(
        self,
        investigator: FailureInvestigator,
        *,
        max_parallel: int,
    ) -> None:
        """Initialize with direct evidence access and bounded API concurrency."""
        self._investigator = investigator
        self._max_parallel = max_parallel

    async def triage(
        self,
        failures: tuple[AirflowFailure, ...],
    ) -> tuple[tuple[AirflowFailure, FailureDiagnosis], ...]:
        """Resolve a batch through direct APIs and inspect logs only as needed."""
        async with traced_operation(
            "agent.prod-support-triage-manager",
            attributes={
                "q2.agent.name": "TriageManager",
                "q2.agent.failure_count": len(failures),
            },
        ):
            semaphore = asyncio.Semaphore(self._max_parallel)

            async def investigate(
                failure: AirflowFailure,
            ) -> tuple[AirflowFailure, FailureDiagnosis]:
                async with semaphore:
                    return await self._investigator.investigate(failure)

            return tuple(
                await asyncio.gather(*(investigate(failure) for failure in failures))
            )
