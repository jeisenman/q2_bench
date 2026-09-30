"""Tests for omission visibility across production-support audiences."""

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
from workspaces.data_engineering.workflows.prod_support.reporting_config import (
    ProdSupportReportConfig,
)

NAMED_ID = "621d1ad2-3d0f-4fc4-8245-e3878a6bff7c"


def _failure(dag_id: str, task_id: str, try_number: int = 1) -> AirflowFailure:
    return AirflowFailure(
        region=Region.US_01,
        dag_id=dag_id,
        run_id="run",
        task_id=task_id,
        start_at=datetime(2026, 9, 26, 5, tzinfo=UTC),
        end_at=datetime(2026, 9, 26, 6, tzinfo=UTC),
        try_number=try_number,
    )


def test_default_omissions_only_hide_jobs_from_data_internal() -> None:
    failures = (
        _failure("subscriber_validation", "check_for_subscriber_client_errors"),
        _failure("log_cleanup", "expire-logs-3"),
        _failure("delivery_to_promise", "D2P"),
        _failure(
            "market_insights_3_output",
            f"client_specific.mi_3_raw_output_validation_{NAMED_ID}",
            6,
        ),
    )
    diagnoses = tuple(
        FailureDiagnosis(
            failure.failure_id,
            FailureKind.APPLICATION_ERROR,
            "confirmed",
            ("terminal error",),
        )
        for failure in failures
    )
    identity = AgentResult(
        output="Andi Application Owner",
        correlation_id=NAMED_ID,
        attributes=(
            ("identifier_value", NAMED_ID),
            ("client_name", "Andi Application Owner"),
            ("status", "unique"),
        ),
    )

    reports = format_reports_with_context(
        date(2026, 9, 26),
        failures,
        diagnoses,
        context=ProdSupportReportContext(resource_discovery_results=(identity,)),
    )

    assert "MI3" in reports.developer
    assert "subscriber" in reports.developer
    assert "log_cleanup" not in reports.developer
    assert "D2P" in reports.developer
    assert "US\n\n- Good\n  - check_for_subscriber_client_errors, D2P, MI3" in (
        reports.data_internal
    )
    assert "MI3" in reports.data_internal
    assert "D2P" in reports.data_internal
    assert "Would you like to re-run:" in reports.follow_up
    assert "MI3" in reports.follow_up
    assert "check_for_subscriber_client_errors" in reports.follow_up
    assert "expire-logs-3" not in reports.follow_up
    for omitted in (
        "check-for-subscriber-client-errors",
        "log_cleanup",
        "expire-logs-3",
        "KPO sizing",
    ):
        assert omitted not in reports.data_internal


def test_subscriber_stays_on_omitted_line_without_recovery_success() -> None:
    failure = _failure(
        "event_bus_to_payloads_historical",
        "check_for_subscriber_client_errors",
    )
    diagnosis = FailureDiagnosis(
        failure.failure_id,
        FailureKind.APPLICATION_ERROR,
        "confirmed",
        ("subscriber validation failed",),
    )
    config = ProdSupportReportConfig().with_verified_omissions(())

    reports = format_reports_with_context(
        date(2026, 9, 29),
        (failure,),
        (diagnosis,),
        context=ProdSupportReportContext(config=config),
    )

    assert "US\n\n- Good\n  - check_for_subscriber_client_errors, D2P, MI3" in (
        reports.data_internal
    )
    assert "Subscriber validation failed on" not in reports.data_internal
