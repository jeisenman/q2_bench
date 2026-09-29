import asyncio
from datetime import UTC, datetime

from workspaces.data_engineering.workflows.prod_support import (
    AirflowFailure,
    ProductionSupportWorkflow,
)
from workspaces.data_engineering.workflows.prod_support.models import Region


class ReplayDay:
    """Replay an exhaustive mixed-day failure capture."""

    def __init__(self, failures: tuple[AirflowFailure, ...]) -> None:
        self.failures = failures

    async def discover_failures(self, since: datetime) -> tuple[AirflowFailure, ...]:
        del since
        return self.failures

    async def fetch_log(self, failure: AirflowFailure) -> str:
        return failure.log


def test_full_day_replay_filters_classifies_and_formats_all_failures() -> None:
    old = AirflowFailure(
        Region.US_01,
        "old-dag",
        "old-run",
        "old-task",
        datetime(2026, 9, 23, 3, tzinfo=UTC),
        datetime(2026, 9, 23, 4, tzinfo=UTC),
        log="old distractor",
    )
    spark = AirflowFailure(
        Region.US_01,
        "spark-dag",
        "spark-run",
        "spark-task",
        datetime(2026, 9, 24, 10, tzinfo=UTC),
        datetime(2026, 9, 24, 11, tzinfo=UTC),
        log="Distinctness validation failed for DepositFinancialStatementsBreakdown",
    )
    batch = AirflowFailure(
        Region.CA_02,
        "batch-dag",
        "batch-run",
        "batch-task",
        datetime(2026, 9, 24, 12, tzinfo=UTC),
        datetime(2026, 9, 24, 13, tzinfo=UTC),
        log="Traceback: application failure",
    )
    agent = ProductionSupportWorkflow(
        ReplayDay((old, spark, batch)),
        clock=lambda: datetime(2026, 9, 25, 12, tzinfo=UTC),
    )

    outcome = asyncio.run(agent.investigate("do today's prod support"))

    assert {failure.dag_id for failure in outcome.failures} == {
        "spark-dag",
        "batch-dag",
    }
    assert {diagnosis.kind.value for diagnosis in outcome.diagnoses} == {
        "distinctness",
        "application_error",
    }
    assert "airflow-us01.precisionlender.com" in outcome.report
    assert "airflow-ca02.precisionlender.com" in outcome.report
    assert "old-dag" not in outcome.report
