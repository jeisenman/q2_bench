import asyncio
from datetime import UTC, datetime

import pytest

from workspaces.data_engineering.agents.production_support import (
    AirflowFailure,
    ClientFailureWorkflow,
    ClientInvestigationError,
)
from workspaces.data_engineering.agents.production_support.models import Region
from workspaces.data_engineering.agents.resource_discovery import (
    ResourceDiscoveryAgent,
    ResourceIdentifier,
)

CLIENT_ID = "8b2e8a38-b778-402a-819a-4904f42f5a2a"
EXPECTED_DAG_ID = f"l3-main-{CLIENT_ID}"


class ExactDagAirflow:
    def __init__(
        self,
        failures: tuple[AirflowFailure, ...],
        events: list[str],
        exact_log: str = "",
    ) -> None:
        self.failures = failures
        self.events = events
        self.exact_log = exact_log
        self.queries: list[tuple[str, datetime]] = []
        self.fetched: list[str] = []

    async def discover_failures(self, since: datetime) -> tuple[AirflowFailure, ...]:
        del since
        raise AssertionError

    async def discover_dag_failures(
        self,
        dag_id: str,
        since: datetime,
    ) -> tuple[AirflowFailure, ...]:
        self.events.append("airflow")
        self.queries.append((dag_id, since))
        return self.failures

    async def fetch_log(self, failure: AirflowFailure) -> str:
        self.fetched.append(failure.failure_id)
        return self.exact_log


class FakeResourceSource:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.identifiers: list[ResourceIdentifier] = []

    async def lookup(
        self,
        identifier: ResourceIdentifier,
    ) -> tuple[dict[str, object], ...]:
        self.events.append("resource_discovery")
        self.identifiers.append(identifier)
        return (
            {
                "provisioned_client_id": identifier.value,
                "client_name": "Valley National Bank",
                "environment": "us01",
            },
        )


def _failure(log: str) -> AirflowFailure:
    return AirflowFailure(
        region=Region.US_01,
        dag_id=EXPECTED_DAG_ID,
        run_id="manual__2026-09-27T05:00:00+00:00",
        task_id=(
            "high_quality_core_account_financial_statements."
            "high_quality_core_account_financial_statements"
        ),
        start_at=datetime(2026, 9, 28, 10, 31, tzinfo=UTC),
        end_at=datetime(2026, 9, 28, 11, 21, tzinfo=UTC),
        try_number=4,
        log=log,
    )


def test_client_investigation_resolves_then_queries_and_parses_exact_log() -> None:
    events: list[str] = []
    exact_log = (
        "Validate distinctness - counts: CoreAccounts - total: 12; unique: 12\n"
        "Validate distinctness - counts: DepositFinancialStatementsBreakdown "
        "- total: 15; unique: 9\n"
        "Distinctness validation failed for "
        "DepositFinancialStatementsBreakdown on account_id"
    )
    source = ExactDagAirflow(
        (_failure(""),),
        events,
        exact_log,
    )
    resource_source = FakeResourceSource(events)
    workflow = ClientFailureWorkflow(
        source,
        resource_discovery=ResourceDiscoveryAgent(resource_source),
        clock=lambda: datetime(2026, 9, 28, 15, tzinfo=UTC),
    )

    result = asyncio.run(workflow.investigate_client_failures(CLIENT_ID))

    assert events == ["resource_discovery", "airflow"]
    assert resource_source.identifiers[0].value == CLIENT_ID
    assert source.queries == [(EXPECTED_DAG_ID, datetime(2026, 9, 27, 5, tzinfo=UTC))]
    assert source.fetched
    assert result["client_name"] == "Valley National Bank"
    assert result["failure_count"] == 1
    failure = result["failures"][0]
    assert failure["classification"] == "distinctness"
    assert "DepositFinancialStatementsBreakdown" in failure["evidence"][0]
    assert failure["distinctness_checks"][0]["status"] == "pass"
    assert failure["distinctness_checks"][1]["status"] == "mismatch"
    assert failure["rerun_targets"] == [
        "ra_group.get_deposit_financial_statement_breakdown"
    ]
    assert "ra_group.get_deposit_financial_statement_breakdown" in result["summary"]
    assert "Would you like to re-run" in result["follow_up"]
    assert "ra_group.get_deposit_financial_statement_breakdown" in result["follow_up"]
    assert result["mutation_performed"] is False


def test_client_investigation_rejects_noncanonical_uuid_before_reads() -> None:
    events: list[str] = []
    source = ExactDagAirflow((), events)
    workflow = ClientFailureWorkflow(source)

    with pytest.raises(ClientInvestigationError, match="canonical"):
        asyncio.run(
            workflow.investigate_client_failures("8b2e8a38b778402a819a4904f42f5a2a")
        )

    assert events == []


def test_client_investigation_reports_no_matching_failures() -> None:
    events: list[str] = []
    workflow = ClientFailureWorkflow(
        ExactDagAirflow((), events),
        clock=lambda: datetime(2026, 9, 28, 15, tzinfo=UTC),
    )

    result = asyncio.run(
        workflow.investigate_client_failures(
            CLIENT_ID,
            since="2026-09-28T05:00:00Z",
        )
    )

    assert result["failure_count"] == 0
    assert "No failed task instances were found" in result["summary"]
    assert result["follow_up"] == "- No action is required."
