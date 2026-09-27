"""Tests for omission visibility across production-support audiences."""

from datetime import UTC, date, datetime

from domain import AgentResult
from workspaces.data_engineering.agents.production_support.models import (
    AirflowFailure,
    FailureDiagnosis,
    FailureKind,
    Region,
)
from workspaces.data_engineering.agents.production_support.reporting import (
    ProdSupportReportContext,
    format_reports_with_context,
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


def test_default_omissions_hide_jobs_from_data_internal_and_follow_up() -> None:
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
    assert "log_cleanup" in reports.developer
    assert "US\n- Ongoing\n  - MI3, D2P\n\nCA\n- Good" in reports.data_internal
    assert reports.data_internal.count("MI3") == 1
    assert reports.data_internal.count("D2P") == 1
    for omitted in (
        "check_for_subscriber_client_errors",
        "check-for-subscriber-client-errors",
        "log_cleanup",
        "expire-logs-3",
        "KPO sizing",
    ):
        assert omitted not in reports.data_internal
        assert omitted not in reports.follow_up
    assert reports.follow_up == "- No action is required."
