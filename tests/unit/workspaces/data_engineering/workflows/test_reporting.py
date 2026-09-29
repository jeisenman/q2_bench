from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from domain import AgentResult
from workspaces.data_engineering.workflows.prod_support.models import (
    AirflowFailure,
    FailureDiagnosis,
    FailureKind,
    Region,
)
from workspaces.data_engineering.workflows.prod_support.reporting import (
    ProdSupportReportContext,
    format_report,
    format_reports_with_context,
)
from workspaces.data_engineering.workflows.prod_support.reporting_config import (
    ProdSupportReportConfig,
)

EXPECTED_URL_SECTION_LINE_COUNT = 3


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


def test_reports_likely_oom_and_kpo_handoff_after_five_attempts() -> None:
    failure = _failure(6)
    diagnosis = FailureDiagnosis(
        failure_id=failure.failure_id,
        kind=FailureKind.UNKNOWN_RESOURCE_TERMINATION,
        confidence="likely_oom",
        evidence=("exit code -9",),
    )

    report = format_report(date(2026, 9, 24), (failure,), (diagnosis,))

    assert "unknown resource termination without corroborating OOM evidence" in report
    assert "[KPO sizing agent](agent://kpo-sizer/definition)" in report


def test_does_not_offer_kpo_handoff_before_sixth_attempt() -> None:
    failure = _failure(5)
    diagnosis = FailureDiagnosis(
        failure_id=failure.failure_id,
        kind=FailureKind.UNKNOWN_RESOURCE_TERMINATION,
        confidence="likely_oom",
        evidence=("exit code -9",),
    )

    report = format_report(date(2026, 9, 24), (failure,), (diagnosis,))

    assert "KPO sizing agent" not in report


def test_formats_channel_reports_and_suggestion_only_follow_up() -> None:
    failure = _failure(4)
    diagnosis = FailureDiagnosis(
        failure_id=failure.failure_id,
        kind=FailureKind.DISTINCTNESS,
        confidence="confirmed",
        evidence=("distinctness failed",),
    )

    reports = format_reports_with_context(date(2026, 9, 24), (failure,), (diagnosis,))

    assert reports.combined.startswith(
        "# Prod Support Report — 2026-09-24 operational day\n\n"
        "Failure cutoff: task instances with `end_date` at or after "
        "`2026-09-24 05:00:00 UTC`"
    )
    assert reports.capture_summary == (
        "Local capture contains 1 failure, all from US-01; "
        "no CA failures were recorded."
    )
    assert reports.urls_to_validate.startswith("URLs to validate\n")
    assert len(reports.urls_to_validate.splitlines()) == EXPECTED_URL_SECTION_LINE_COUNT
    assert reports.developer.startswith("Message for developer:\n  -")
    assert "/grid?" not in reports.urls_to_validate
    assert reports.data_internal.startswith(
        ":bangbang: PROD SUPPORT 2026-09-24 :bangbang:"
    )
    assert "." not in reports.data_internal
    assert reports.follow_up.startswith("- Would you like to re-run:")
    assert "l3-main-client relationship_signals job" in reports.follow_up
    assert "Follow Ups:" in reports.combined
    assert "Message for Data Internal Channel" not in reports.combined


def test_developer_report_lists_every_failure() -> None:
    us_failure = _failure(1)
    ca_failure = replace(
        us_failure,
        region=Region.CA_02,
        dag_id="ca-dag",
        task_id="ca-task",
    )
    diagnoses = tuple(
        FailureDiagnosis(
            failure_id=failure.failure_id,
            kind=FailureKind.APPLICATION_ERROR,
            confidence="confirmed",
            evidence=(f"{failure.task_id} failed",),
        )
        for failure in (us_failure, ca_failure)
    )

    reports = format_reports_with_context(
        date(2026, 9, 24),
        (us_failure, ca_failure),
        diagnoses,
    )

    assert "l3-main-client failed on relationship_signals" in reports.developer
    assert "ca-dag failed on ca-task" in reports.developer
    assert "\n\n  -" not in reports.developer
    assert "US\n- Ongoing\n  - l3-main-client failed on" in reports.data_internal
    assert "\n\nCA\n- Ongoing\n  - ca-dag failed on" in reports.data_internal
    assert reports.capture_summary == (
        "Local capture contains 2 failures: 1 from US-01 and 1 from CA-02."
    )


def test_reports_group_named_clients_that_fail_the_same_job() -> None:
    client_a = "11111111-1111-4111-8111-111111111111"
    client_b = "22222222-2222-4222-8222-222222222222"
    failures = tuple(
        replace(
            _failure(1),
            dag_id=f"l3-main-{client_id}",
            task_id="opportunity_save_history.opportunity_save_history",
        )
        for client_id in (client_a, client_b)
    )
    diagnoses = tuple(
        FailureDiagnosis(
            failure_id=failure.failure_id,
            kind=FailureKind.APPLICATION_ERROR,
            confidence="confirmed",
            evidence=("terminal application error",),
        )
        for failure in failures
    )
    resources = (
        _resource_result(client_a, "Client A"),
        _resource_result(client_b, "Client B"),
    )

    reports = format_reports_with_context(
        date(2026, 9, 24),
        failures,
        diagnoses,
        context=ProdSupportReportContext(resource_discovery_results=resources),
    )

    grouped = "Client A (111) and Client B (222) failed on opportunity_save_history"
    assert reports.developer.count(grouped) == 1
    assert reports.data_internal.count(grouped) == 1
    assert (
        "  - Client A (111) l3-main-11111111-1111-4111-8111-111111111111 "
        "opportunity_save_history job"
    ) in reports.follow_up
    assert (
        "  - Client B (222) l3-main-22222222-2222-4222-8222-222222222222 "
        "opportunity_save_history job"
    ) in reports.follow_up


def test_reports_task_embedded_client_name_and_unresolved_identity() -> None:
    named_id = "621d1ad2-3d0f-4fc4-8245-e3878a6bff7c"
    unresolved_id = "33333333-3333-4333-8333-333333333333"
    named = replace(
        _failure(1),
        dag_id="market_insights_3_output",
        task_id=f"client_specific.mi_3_raw_output_validation_{named_id}",
    )
    unresolved = replace(
        _failure(1),
        dag_id=f"l3-main-{unresolved_id}",
        task_id="credit_migration_matrix.credit_migration_matrix",
    )
    diagnoses = tuple(
        FailureDiagnosis(
            failure_id=failure.failure_id,
            kind=FailureKind.APPLICATION_ERROR,
            confidence="confirmed",
            evidence=("terminal error",),
        )
        for failure in (named, unresolved)
    )

    reports = format_reports_with_context(
        date(2026, 9, 24),
        (named, unresolved),
        diagnoses,
        context=ProdSupportReportContext(
            resource_discovery_results=(
                _resource_result(named_id, "Andi Application Owner"),
                _resource_result(unresolved_id, None, status="not_found"),
            ),
        ),
    )

    assert "Andi Application Owner (621) failed on MI3" in reports.developer
    assert "Unresolved client (333)" in reports.developer
    assert "Resource Discovery: no reviewed unique match (not_found)" in (
        reports.developer
    )
    assert "Ask a human to resolve the client identity for Unresolved client (333)" in (
        reports.follow_up
    )
    assert "Andi Application Owner (621)" in reports.follow_up
    assert "Unresolved client (333):" not in reports.follow_up


def test_empty_omission_override_includes_every_job() -> None:
    failure = replace(
        _failure(1),
        task_id="delivery_to_promise.delivery_to_promise_data",
    )
    diagnosis = FailureDiagnosis(
        failure_id=failure.failure_id,
        kind=FailureKind.APPLICATION_ERROR,
        confidence="confirmed",
        evidence=("terminal error",),
    )

    reports = format_reports_with_context(
        date(2026, 9, 24),
        (failure,),
        (diagnosis,),
        context=ProdSupportReportContext(
            config=ProdSupportReportConfig.from_omission_values(())
        ),
    )

    assert "US\n- Ongoing\n  - l3-main-client failed on D2P" in reports.data_internal
    assert "l3-main-client delivery_to_promise_data job" in reports.follow_up


def test_large_resend_uses_raw_log_count_and_pd_rix_follow_up() -> None:
    client_id = "11111111-1111-4111-8111-111111111111"
    failure = replace(
        _failure(2),
        dag_id=f"l3-main-{client_id}",
        run_id="manual__2026-09-22T05:00:00+00:00",
        task_id="validate_event_bus_opportunities",
        log="Reported 12,471 unique missing opportunity snapshots",
    )
    diagnosis = FailureDiagnosis(
        failure_id=failure.failure_id,
        kind=FailureKind.APPLICATION_ERROR,
        confidence="confirmed",
        evidence=("AirflowTaskTimeout",),
    )

    reports = format_reports_with_context(
        date(2026, 9, 24),
        (failure,),
        (diagnosis,),
        context=ProdSupportReportContext(
            resource_discovery_results=(_resource_result(client_id, "Bank of Hope"),)
        ),
    )

    assert (
        "Bank of Hope (111) failed on validate_event_bus_opportunities"
        in reports.data_internal
    )
    assert (
        "Follow up with pd-rix about 12,471 opportunities "
        "for Bank of Hope (111) for date 09-22-26."
    ) in reports.follow_up
    assert "Ask a human to identify the production resend application" in (
        reports.follow_up
    )


def test_resend_follow_up_uses_resource_discovery_link() -> None:
    client_id = "11111111-1111-4111-8111-111111111111"
    failure = replace(
        _failure(1),
        dag_id=f"l3-main-{client_id}",
        run_id="manual__2026-09-22T05:00:00+00:00",
        task_id="validate_event_bus_opportunities",
    )
    diagnosis = FailureDiagnosis(
        failure_id=failure.failure_id,
        kind=FailureKind.APPLICATION_ERROR,
        confidence="confirmed",
        evidence=("3 missing opportunity snapshots",),
    )

    reports = format_reports_with_context(
        date(2026, 9, 24),
        (failure,),
        (diagnosis,),
        context=ProdSupportReportContext(
            resource_discovery_results=(
                _resource_result(
                    client_id,
                    "Bank of Hope",
                    environment="ca02",
                    reviewed_resend_url=(
                        "https://cac01-app.precisionlender.com/"
                        "Admin/Troubleshooting/ResendSnapshotsForClient"
                    ),
                ),
            ),
        ),
    )

    assert (
        "Send events for Bank of Hope (111) on "
        "[Resend Opportunity Snapshots](https://cac01-app.precisionlender.com/"
        "Admin/Troubleshooting/ResendSnapshotsForClient) for date 09-22-26."
    ) in reports.follow_up


@pytest.mark.parametrize(
    ("values", "message"),
    [
        (("unknown",), "unsupported Data Internal omission"),
        (("d2p", "d2p"), "duplicate Data Internal omission"),
        (("",), "must contain non-empty strings"),
    ],
)
def test_report_configuration_rejects_invalid_omissions(
    values: tuple[str, ...],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ProdSupportReportConfig.from_omission_values(values)


def _resource_result(
    client_id: str,
    client_name: str | None,
    *,
    status: str = "unique",
    environment: str | None = None,
    reviewed_resend_url: str | None = None,
) -> AgentResult:
    return AgentResult(
        output="resource result",
        correlation_id=f"resource-{client_id}",
        attributes=(
            ("identifier_value", client_id),
            ("client_name", client_name),
            ("status", status),
            ("environment", environment),
            ("reviewed_production_resend_url", reviewed_resend_url),
        ),
    )
