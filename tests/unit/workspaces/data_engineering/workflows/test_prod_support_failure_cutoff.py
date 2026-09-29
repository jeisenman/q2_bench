"""Regression tests for production-support failure cutoff behavior."""

import asyncio
from datetime import UTC, datetime

from workspaces.data_engineering.workflows.prod_support import (
    AirflowFailure,
    ProductionSupportWorkflow,
    Region,
)


class FailureSource:
    """Return deterministic Airflow failures for cutoff tests."""

    def __init__(self, failures: tuple[AirflowFailure, ...]) -> None:
        self.failures = failures
        self.requested_since: datetime | None = None

    async def discover_failures(
        self,
        since: datetime,
    ) -> tuple[AirflowFailure, ...]:
        self.requested_since = since
        return self.failures

    async def fetch_log(self, failure: AirflowFailure) -> str:
        return failure.log


def test_workflow_keeps_failure_ending_after_next_operational_anchor() -> None:
    failure = AirflowFailure(
        region=Region.US_01,
        dag_id="l3-main-client",
        run_id="manual__2026-09-28T05:00:00+00:00",
        task_id="delivery_to_promise.delivery_to_promise_data",
        start_at=datetime(2026, 9, 29, 11, 30, tzinfo=UTC),
        end_at=datetime(2026, 9, 29, 14, 11, tzinfo=UTC),
        log="terminal application failure",
    )
    source = FailureSource((failure,))
    workflow = ProductionSupportWorkflow(
        source,
        clock=lambda: datetime(2026, 9, 29, 18, tzinfo=UTC),
    )

    outcome = asyncio.run(workflow.investigate("run production support for today"))

    assert source.requested_since == datetime(2026, 9, 28, 5, tzinfo=UTC)
    assert outcome.failures == (failure,)
    assert "end_date` at or after `2026-09-28 05:00:00 UTC" in outcome.report
    assert "_flt_1_end_date" not in outcome.report
