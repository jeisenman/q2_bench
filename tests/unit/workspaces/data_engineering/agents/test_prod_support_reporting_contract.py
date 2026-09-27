from datetime import UTC, date, datetime

import pytest

from domain import AgentResult
from workspaces.data_engineering.agents.production_support import (
    AirflowFailure,
    ClusterHealthState,
    ClusterHealthValueError,
    FailureDiagnosis,
    ProdSupportReportContext,
    Region,
    RegionalClusterHealth,
)
from workspaces.data_engineering.agents.production_support.models import FailureKind
from workspaces.data_engineering.agents.production_support.reporting import (
    format_reports,
    format_reports_with_context,
)
from workspaces.data_engineering.agents.production_support.reporting_validation import (
    ReportContractError,
)

MAX_DATA_INTERNAL_BULLET_CHARACTERS = 180
EXPECTED_REGION_COUNT = 2


def _failure(
    client_id: str,
    *,
    region: Region = Region.CA_02,
    task_id: str = "opportunity_save_history.run",
) -> AirflowFailure:
    return AirflowFailure(
        region=region,
        dag_id=f"l3-main-{client_id}",
        run_id="manual__2026-09-25T05:00:00+00:00",
        task_id=task_id,
        start_at=datetime(2026, 9, 25, 5, tzinfo=UTC),
        end_at=datetime(2026, 9, 25, 6, tzinfo=UTC),
    )


def _diagnosis(
    failure: AirflowFailure,
    evidence: str = "Exception: terminal",
) -> FailureDiagnosis:
    return FailureDiagnosis(
        failure_id=failure.failure_id,
        kind=FailureKind.APPLICATION_ERROR,
        confidence="confirmed",
        evidence=(evidence,),
    )


def _resource(
    client_id: str,
    name: str | None,
    *,
    status: str = "unique",
) -> AgentResult:
    return AgentResult(
        output="resource",
        correlation_id=client_id,
        attributes=(
            ("identifier_value", client_id),
            ("client_name", name),
            ("status", status),
            ("environment", "ca02"),
        ),
    )


def _healthy(
    region: Region,
    count: int,
    *,
    warnings: tuple[str, ...] = (),
) -> RegionalClusterHealth:
    return RegionalClusterHealth(
        region=region,
        observed_at=datetime(2026, 9, 26, 17, tzinfo=UTC),
        application_healthy=True,
        pods_healthy=True,
        dags_parsing_healthy=True,
        active_dag_count=count,
        restart_count=7,
        keda_status="access_denied",
        warnings=warnings,
    )


def test_cluster_warnings_do_not_contradict_primary_healthy_status() -> None:
    reports = format_reports_with_context(
        date(2026, 9, 25),
        (),
        (),
        context=ProdSupportReportContext(
            cluster_health=(
                _healthy(Region.US_01, 209),
                _healthy(
                    Region.CA_02,
                    34,
                    warnings=("one retired DAG processor replica is unready",),
                ),
            )
        ),
    )

    assert "US Cluster Health: healthy" in reports.developer
    assert "CA Cluster Health: healthy" in reports.developer
    assert reports.developer.count("7 pod restarts") == EXPECTED_REGION_COUNT
    assert "DAGs parsing properly: 209 DAGs exist in US, 34 DAGs exist in CA" in (
        reports.developer
    )
    assert "cluster is unhealthy" not in reports.data_internal
    assert "US\n- Good\nCA\n- Good" in reports.data_internal


def test_unhealthy_cluster_is_reported_only_in_its_region() -> None:
    ca_health = RegionalClusterHealth(
        region=Region.CA_02,
        application_healthy=True,
        pods_healthy=False,
        dags_parsing_healthy=True,
        active_dag_count=34,
        symptoms=("scheduler pods are unready", "task launches are stalled"),
    )
    reports = format_reports_with_context(
        date(2026, 9, 25),
        (),
        (),
        context=ProdSupportReportContext(
            cluster_health=(_healthy(Region.US_01, 209), ca_health)
        ),
    )

    us_block, ca_block = reports.data_internal.split("\nCA\n", maxsplit=1)
    assert "US\n- Good" in us_block
    assert "cluster is unhealthy" not in us_block
    assert "CA cluster is unhealthy" not in ca_block
    assert "scheduler pods are unready" not in ca_block
    assert "." not in reports.data_internal


def test_ambiguous_resource_name_is_not_treated_as_reviewed_identity() -> None:
    client_id = "11111111-1111-4111-8111-111111111111"
    failure = _failure(client_id)
    reports = format_reports_with_context(
        date(2026, 9, 25),
        (failure,),
        (_diagnosis(failure),),
        context=ProdSupportReportContext(
            resource_discovery_results=(
                _resource(client_id, "Wrong Guess Bank", status="ambiguous"),
            )
        ),
    )

    assert "Wrong Guess Bank" not in reports.developer
    assert "Unresolved client (111)" in reports.developer
    assert "no reviewed unique match (ambiguous)" in reports.developer
    assert (
        "Ask a human to resolve the client identity for Unresolved client (111) "
        "before proposing remediation for date 09-25-26."
    ) in reports.follow_up
    assert "Do you approve re-running" not in reports.follow_up


def test_long_shared_job_groups_split_without_losing_or_repeating_clients() -> None:
    client_ids = tuple(
        f"{index:08d}-1111-4111-8111-111111111111" for index in range(1, 8)
    )
    failures = tuple(_failure(client_id) for client_id in client_ids)
    resources = tuple(
        _resource(client_id, f"Very Long Regional Client Name Number {index}")
        for index, client_id in enumerate(client_ids, start=1)
    )
    reports = format_reports_with_context(
        date(2026, 9, 25),
        failures,
        tuple(_diagnosis(failure) for failure in failures),
        context=ProdSupportReportContext(
            resource_discovery_results=resources,
        ),
    )

    ongoing_lines = tuple(
        line for line in reports.data_internal.splitlines() if line.startswith("  - ")
    )
    assert len(ongoing_lines) > 1
    assert all(
        len(line) <= MAX_DATA_INTERNAL_BULLET_CHARACTERS for line in ongoing_lines
    )
    for index in range(1, 8):
        assert (
            reports.data_internal.count(
                f"Very Long Regional Client Name Number {index}"
            )
            == 1
        )


def test_developer_group_preserves_different_evidence_per_client() -> None:
    first_id = "11111111-1111-4111-8111-111111111111"
    second_id = "22222222-2222-4222-8222-222222222222"
    first = _failure(first_id)
    second = _failure(second_id)
    reports = format_reports_with_context(
        date(2026, 9, 25),
        (first, second),
        (
            _diagnosis(first, "Exception: first terminal cause"),
            _diagnosis(second, "Exception: second terminal cause"),
        ),
        context=ProdSupportReportContext(
            resource_discovery_results=(
                _resource(first_id, "Client A"),
                _resource(second_id, "Client B"),
            )
        ),
    )

    assert "Client A (111) and Client B (222) failed on opportunity_save_history" in (
        reports.developer
    )
    assert "evidence by failure:" in reports.developer
    assert "first terminal cause" in reports.developer
    assert "second terminal cause" in reports.developer


def test_grid_links_are_separate_from_the_compact_developer_message() -> None:
    client_id = "11111111-1111-4111-8111-111111111111"
    failure = _failure(client_id)
    reports = format_reports(
        date(2026, 9, 25),
        (failure,),
        (_diagnosis(failure),),
    )

    assert "/grid?status=failed" in reports.urls_to_validate
    assert "/grid?status=failed" not in reports.developer


def test_environment_without_reviewed_mapping_does_not_offer_resend() -> None:
    client_id = "11111111-1111-4111-8111-111111111111"
    failure = _failure(
        client_id,
        task_id="validate_event_bus_opportunities",
    )
    reports = format_reports_with_context(
        date(2026, 9, 25),
        (failure,),
        (_diagnosis(failure, "208 missing opportunity snapshots"),),
        context=ProdSupportReportContext(
            resource_discovery_results=(_resource(client_id, "Client A"),)
        ),
    )

    assert (
        "Ask a human to identify the production resend application environment "
        "for Client A (111) for date 09-25-26."
    ) in reports.follow_up
    assert "Resend 208 opportunities" not in reports.follow_up


def test_report_rejects_missing_or_duplicate_structured_evidence() -> None:
    client_id = "11111111-1111-4111-8111-111111111111"
    failure = _failure(client_id)

    with pytest.raises(ReportContractError, match="exactly one matching diagnosis"):
        format_reports_with_context(date(2026, 9, 25), (failure,), ())
    with pytest.raises(ReportContractError, match="duplicate Airflow"):
        format_reports_with_context(
            date(2026, 9, 25),
            (failure, failure),
            (_diagnosis(failure),),
        )
    diagnosis = _diagnosis(failure)
    with pytest.raises(ReportContractError, match="duplicate failure diagnoses"):
        format_reports_with_context(
            date(2026, 9, 25),
            (failure,),
            (diagnosis, diagnosis),
        )
    health = _healthy(Region.US_01, 209)
    with pytest.raises(ReportContractError, match="duplicate regional"):
        format_reports_with_context(
            date(2026, 9, 25),
            (),
            (),
            context=ProdSupportReportContext(cluster_health=(health, health)),
        )


def test_cluster_health_stays_in_developer_report() -> None:
    health = RegionalClusterHealth(
        region=Region.CA_02,
        application_healthy=False,
        pods_healthy=False,
        dags_parsing_healthy=False,
        active_dag_count=0,
    )
    reports = format_reports_with_context(
        date(2026, 9, 25),
        (),
        (),
        context=ProdSupportReportContext(cluster_health=(health,)),
    )

    assert health.state is ClusterHealthState.UNHEALTHY
    assert "CA Cluster Health: unhealthy" in reports.developer
    assert "0 active DAGs" in reports.developer
    assert "cluster" not in reports.data_internal.casefold()


def test_cluster_health_rejects_invalid_observations() -> None:
    with pytest.raises(ClusterHealthValueError, match="timezone-aware"):
        RegionalClusterHealth(
            region=Region.US_01,
            observed_at=datetime(2026, 9, 26, 17),
        )
    with pytest.raises(ClusterHealthValueError, match="must not be negative"):
        RegionalClusterHealth(region=Region.US_01, active_dag_count=-1)
    with pytest.raises(ClusterHealthValueError, match="must not be empty"):
        RegionalClusterHealth(region=Region.US_01, keda_status="")
    with pytest.raises(ClusterHealthValueError, match="symptoms and warnings"):
        RegionalClusterHealth(region=Region.US_01, symptoms=("",))
