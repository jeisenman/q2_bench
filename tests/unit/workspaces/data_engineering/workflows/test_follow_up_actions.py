"""Tests for canonical production-support resend follow-up actions."""

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

RESEND_URL = (
    "https://cac01-app.precisionlender.com/"
    "Admin/Troubleshooting/ResendSnapshotsForClient"
)


def test_groups_clients_by_date_and_link_with_deduplicated_opportunity_count() -> None:
    first = _failure(
        "11111111-1111-4111-8111-111111111111",
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    )
    second = _failure(
        "22222222-2222-4222-8222-222222222222",
        "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    )

    reports = format_reports_with_context(
        date(2026, 9, 26),
        (first, second),
        (_diagnosis(first), _diagnosis(second)),
        context=ProdSupportReportContext(
            resource_discovery_results=(
                _resource(first, "Client One"),
                _resource(second, "Client Two"),
            )
        ),
    )

    assert (
        "Send events for Client One (111) and Client Two (222) on "
        f"[Resend Opportunity Snapshots]({RESEND_URL}) for date 09-18-26."
    ) in reports.follow_up
    assert "recoverable opportunities" not in reports.follow_up


def _failure(client_id: str, opportunity_id: str) -> AirflowFailure:
    repeated_payload = (
        f"OpportunityId: {opportunity_id}\n"
        f"OpportunityId: {opportunity_id}\n"
        "Is Recoverable: True"
    )
    return AirflowFailure(
        region=Region.CA_02,
        dag_id=f"l3-main-{client_id}",
        run_id="manual__2026-09-18T05:00:00+00:00",
        task_id="validate_event_bus_opportunities",
        start_at=datetime(2026, 9, 26, 19, tzinfo=UTC),
        end_at=datetime(2026, 9, 26, 20, tzinfo=UTC),
        log=repeated_payload,
    )


def _diagnosis(failure: AirflowFailure) -> FailureDiagnosis:
    return FailureDiagnosis(
        failure_id=failure.failure_id,
        kind=FailureKind.APPLICATION_ERROR,
        confidence="confirmed",
        evidence=("Unhandled Exception",),
    )


def _resource(failure: AirflowFailure, name: str) -> AgentResult:
    client_id = failure.dag_id.removeprefix("l3-main-")
    return AgentResult(
        output="resource",
        correlation_id=client_id,
        attributes=(
            ("identifier_value", client_id),
            ("client_name", name),
            ("status", "unique"),
            ("environment", "ca02"),
            ("reviewed_production_resend_url", RESEND_URL),
        ),
    )
