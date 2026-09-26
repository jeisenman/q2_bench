from datetime import UTC, date, datetime

from workspaces.data_engineering.agents.prod_support.models import (
    AirflowFailure,
    FailureDiagnosis,
    FailureKind,
    Region,
)
from workspaces.data_engineering.agents.prod_support.reporting import (
    format_report,
    format_reports,
)


def _failure(try_number: int) -> AirflowFailure:
    return AirflowFailure(
        region=Region.US_01,
        dag_id="l3-main-client",
        run_id="run",
        task_id="relationship_signals",
        start_at=datetime(2026, 9, 24, 5, tzinfo=UTC),
        end_at=datetime(2026, 9, 24, 6, tzinfo=UTC),
        try_number=try_number,
    )


def test_reports_likely_oom_and_ticket_after_five_attempts() -> None:
    failure = _failure(6)
    diagnosis = FailureDiagnosis(
        failure_id=failure.failure_id,
        kind=FailureKind.UNKNOWN_RESOURCE_TERMINATION,
        confidence="likely_oom",
        evidence=("exit code -9",),
    )

    report = format_report(date(2026, 9, 24), (failure,), (diagnosis,))

    assert "unknown_resource_termination: likely OOMed" in report
    assert "-- making ticket to fix" in report


def test_does_not_make_ticket_before_sixth_attempt() -> None:
    failure = _failure(5)
    diagnosis = FailureDiagnosis(
        failure_id=failure.failure_id,
        kind=FailureKind.UNKNOWN_RESOURCE_TERMINATION,
        confidence="likely_oom",
        evidence=("exit code -9",),
    )

    report = format_report(date(2026, 9, 24), (failure,), (diagnosis,))

    assert "-- making ticket to fix" not in report


def test_formats_channel_reports_and_suggestion_only_follow_up() -> None:
    failure = _failure(4)
    diagnosis = FailureDiagnosis(
        failure_id=failure.failure_id,
        kind=FailureKind.DISTINCTNESS,
        confidence="confirmed",
        evidence=("distinctness failed",),
    )

    reports = format_reports(date(2026, 9, 24), (failure,), (diagnosis,))

    assert reports.developer.startswith("Message for Developer")
    assert reports.data_internal.startswith("Message for Data Internal Channel")
    assert "Would you like me to prepare retry recommendations" in reports.follow_up
    assert "attempt 4" in reports.follow_up
    assert "Message for Data Internal Channel" in reports.combined
