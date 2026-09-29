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


def _failure(
    client_id: str,
    task_id: str,
    *,
    region: Region = Region.CA_02,
) -> AirflowFailure:
    return AirflowFailure(
        region=region,
        dag_id=f"l3-main-{client_id}",
        run_id="manual__2026-09-24T05:00:00+00:00",
        task_id=task_id,
        start_at=datetime(2026, 9, 25, 10, tzinfo=UTC),
        end_at=datetime(2026, 9, 25, 11, tzinfo=UTC),
    )


def _diagnosis(
    failure: AirflowFailure,
    kind: FailureKind = FailureKind.APPLICATION_ERROR,
) -> FailureDiagnosis:
    return FailureDiagnosis(
        failure_id=failure.failure_id,
        kind=kind,
        confidence="confirmed",
        evidence=("terminal evidence",),
    )


def _resource(client_id: str, name: str) -> AgentResult:
    return AgentResult(
        output=name,
        correlation_id=client_id,
        attributes=(
            ("identifier_value", client_id),
            ("client_name", name),
            ("status", "unique"),
            ("environment", "ca02"),
        ),
    )


def test_groups_multiple_jobs_for_one_client() -> None:
    client_id = "11111111-1111-4111-8111-111111111111"
    failures = (
        _failure(client_id, "opportunity_save_history.opportunity_save_history"),
        _failure(client_id, "opportunities_report.library_opportunities"),
        _failure(client_id, "relationship_quandrants.relationship_quandrants"),
    )

    report = format_reports_with_context(
        date(2026, 9, 25),
        failures,
        tuple(_diagnosis(item) for item in failures),
        context=ProdSupportReportContext(
            resource_discovery_results=(_resource(client_id, "Client A"),)
        ),
    )

    expected = (
        "Client A (111) failed on opportunity_save_history, "
        "opportunities_report, and relationship_quandrants"
    )
    assert report.data_internal.count(expected) == 1
    assert report.data_internal.count("Client A (111)") == 1
    assert report.developer.count("Client A (111)") == 1


def test_same_job_never_crosses_regional_sections() -> None:
    client_id = "11111111-1111-4111-8111-111111111111"
    us_failure = _failure(
        client_id,
        "opportunity_save_history.opportunity_save_history",
        region=Region.US_01,
    )
    ca_failure = replace(us_failure, region=Region.CA_02)

    report = format_reports_with_context(
        date(2026, 9, 25),
        (us_failure, ca_failure),
        (_diagnosis(us_failure), _diagnosis(ca_failure)),
        context=ProdSupportReportContext(
            resource_discovery_results=(_resource(client_id, "Client A"),)
        ),
    )

    us_block, ca_block = report.data_internal.split("\nCA\n", maxsplit=1)
    assert us_block.count("Client A (111)") == 1
    assert ca_block.count("Client A (111)") == 1


def test_groups_shared_job_even_when_one_client_has_another_failure() -> None:
    client_a = "11111111-1111-4111-8111-111111111111"
    client_b = "22222222-2222-4222-8222-222222222222"
    shared_a = _failure(client_a, "opportunity_save_history.run")
    shared_b = _failure(client_b, "opportunity_save_history.run")
    extra_a = _failure(client_a, "opportunities_report.run")
    failures = (shared_a, shared_b, extra_a)

    report = format_reports_with_context(
        date(2026, 9, 25),
        failures,
        tuple(_diagnosis(item) for item in failures),
        context=ProdSupportReportContext(
            resource_discovery_results=(
                _resource(client_a, "Client A"),
                _resource(client_b, "Client B"),
            ),
        ),
    )

    assert (
        "Client A (111) and Client B (222) failed on opportunity_save_history"
        in report.data_internal
    )
    assert "Client A (111) failed on opportunities_report" in report.data_internal
    assert report.data_internal.count("opportunity_save_history") == 1


def test_data_internal_retains_high_value_causes() -> None:
    clients = (
        "11111111-1111-4111-8111-111111111111",
        "22222222-2222-4222-8222-222222222222",
        "33333333-3333-4333-8333-333333333333",
    )
    kinds = (
        FailureKind.CONFIRMED_OOM,
        FailureKind.AIRFLOW_CONFIRMED_TIMEOUT,
        FailureKind.DISTINCTNESS,
    )
    failures = tuple(
        _failure(client_id, f"job_{index}") for index, client_id in enumerate(clients)
    )

    report = format_reports_with_context(
        date(2026, 9, 25),
        failures,
        tuple(
            _diagnosis(failure, kind)
            for failure, kind in zip(failures, kinds, strict=True)
        ),
        context=ProdSupportReportContext(
            resource_discovery_results=tuple(
                _resource(client_id, f"Client {index}")
                for index, client_id in enumerate(clients)
            )
        ),
    )

    assert "with OOM" in report.data_internal
    assert "with timeout" in report.data_internal
    assert "failed DV" in report.data_internal


def test_cmm_is_excluded_from_data_internal_and_follow_up_by_default() -> None:
    client_id = "11111111-1111-4111-8111-111111111111"
    failure = _failure(
        client_id,
        "credit_migration_matrix.credit_migration_matrix",
    )

    report = format_reports_with_context(
        date(2026, 9, 25),
        (failure,),
        (_diagnosis(failure),),
        context=ProdSupportReportContext(
            resource_discovery_results=(_resource(client_id, "Client A"),)
        ),
    )

    assert "CMM" in report.developer
    assert "CA\n- Good" in report.data_internal
    assert "CMM" not in report.data_internal
    assert "Client A (111)" not in report.data_internal
    assert "Do you approve re-running" not in report.follow_up


def test_mi3_and_d2p_omissions_are_summarized() -> None:
    client_id = "11111111-1111-4111-8111-111111111111"
    failures = (
        _failure(client_id, "delivery_to_promise.delivery_to_promise_data"),
        _failure(client_id, "delivery_to_promise_other_products.run"),
        _failure(client_id, "market_insights_3.run"),
    )

    report = format_reports_with_context(
        date(2026, 9, 25),
        failures,
        tuple(_diagnosis(item) for item in failures),
        context=ProdSupportReportContext(
            resource_discovery_results=(_resource(client_id, "Client A"),)
        ),
    )

    assert (
        "CA\n- Ongoing\n- check_for_subscriber_client_errors, D2P, MI3"
        in report.data_internal
    )
    assert "Client A (111)" not in report.data_internal
