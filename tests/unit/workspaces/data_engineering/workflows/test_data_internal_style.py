from dataclasses import replace
from datetime import UTC, date, datetime

from domain import AgentResult
from workspaces.data_engineering.workflows.prod_support.models import (
    AirflowFailure,
    FailureDiagnosis,
    FailureKind,
    Region,
)
from workspaces.data_engineering.workflows.prod_support.reporting import (
    ProdSupportReportContext,
    format_reports_with_context,
)

CLIENT_ID = "1f06da19-2f61-401c-a1b7-38902e4f3543"


def failure(task_id: str) -> AirflowFailure:
    return AirflowFailure(
        region=Region.CA_02,
        dag_id=f"l3-main-{CLIENT_ID}",
        run_id=task_id,
        task_id=task_id,
        start_at=datetime(2026, 9, 27, 5, tzinfo=UTC),
        end_at=datetime(2026, 9, 27, 6, tzinfo=UTC),
    )


def test_multi_job_client_row_uses_only_exact_job_identifiers() -> None:
    first = failure("monthly_relationships.monthly_relationships")
    second = replace(
        failure("similar_loans_portfolio.similar_loans_portfolio"),
        start_at=first.end_at,
        end_at=first.end_at,
    )
    diagnoses = (
        FailureDiagnosis(
            first.failure_id,
            FailureKind.APPLICATION_ERROR,
            "confirmed",
            ("missing RA run date",),
        ),
        FailureDiagnosis(
            second.failure_id,
            FailureKind.UNKNOWN,
            "unknown",
            ("unknown terminal cause",),
        ),
    )
    identity = AgentResult(
        output="Scotiabank",
        correlation_id=CLIENT_ID,
        attributes=(
            ("identifier_value", CLIENT_ID),
            ("client_name", "Scotiabank"),
            ("status", "unique"),
        ),
    )

    reports = format_reports_with_context(
        date(2026, 9, 27),
        (first, second),
        diagnoses,
        context=ProdSupportReportContext(resource_discovery_results=(identity,)),
    )

    compliant = (
        "Scotiabank (1f0) failed on monthly_relationships and similar_loans_portfolio"
    )
    assert compliant in reports.data_internal
    assert "missing RA run date" not in reports.data_internal
    assert "unknown terminal cause" not in reports.data_internal
    assert "." not in reports.data_internal


def test_single_job_row_preserves_underscored_identifier() -> None:
    client_id = "49f00000-0000-0000-0000-000000000000"
    failed_task = replace(
        failure("active_deposit_accounts.active_deposit_accounts"),
        region=Region.US_01,
        dag_id=f"l3-main-{client_id}",
    )
    diagnosis = FailureDiagnosis(
        failed_task.failure_id,
        FailureKind.APPLICATION_ERROR,
        "confirmed",
        ("application failure",),
    )
    identity = AgentResult(
        output="Renasant Bank",
        correlation_id=client_id,
        attributes=(
            ("identifier_value", client_id),
            ("client_name", "Renasant Bank"),
            ("status", "unique"),
        ),
    )

    reports = format_reports_with_context(
        date(2026, 9, 27),
        (failed_task,),
        (diagnosis,),
        context=ProdSupportReportContext(resource_discovery_results=(identity,)),
    )

    assert "Renasant Bank (49f) failed on active_deposit_accounts" in (
        reports.data_internal
    )
    assert "active-deposit" not in reports.data_internal
    assert "active deposit" not in reports.data_internal
    assert "." not in reports.data_internal
