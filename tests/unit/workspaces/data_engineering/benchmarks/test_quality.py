from datetime import date

from workspaces.data_engineering.agents.production_support import airflow_failure_url
from workspaces.data_engineering.agents.production_support.models import Region
from workspaces.data_engineering.benchmarks import (
    ComputeKind,
    TaskObservation,
    dag_existence_rate,
    detect_compute_kind,
    failure_recall,
    filter_failures,
    regional_count_accuracy,
)


def test_airflow_links_filter_each_region_at_operational_cutoff() -> None:
    operational_date = date(2026, 9, 24)

    us_url = airflow_failure_url(Region.US_01, operational_date)
    ca_url = airflow_failure_url(Region.CA_02, operational_date)

    assert "airflow-us01.precisionlender.com" in us_url
    assert "airflow-ca02.precisionlender.com" in ca_url
    assert "_flt_3_state=failed" in us_url
    assert "_flt_1_end_date=2026-09-25T05:00:00Z" in us_url
    assert "_flt_2_end_date=2026-09-24T05:00:00Z" in us_url
    assert "%" not in us_url


def test_airflow_links_bound_historical_dates_to_one_day() -> None:
    url = airflow_failure_url(
        Region.US_01,
        date(2026, 9, 23),
        reference_date=date(2026, 9, 25),
    )

    assert "_flt_1_end_date=2026-09-24T05:00:00Z" in url
    assert "_flt_2_end_date=2026-09-23T05:00:00Z" in url


def test_filter_failures_excludes_successes() -> None:
    tasks = (
        TaskObservation("success", "success"),
        TaskObservation("failed", "failed"),
        TaskObservation("running", "running"),
    )

    assert filter_failures(tasks) == (TaskObservation("failed", "failed"),)


def test_failure_recall_requires_every_expected_job() -> None:
    expected = {"one", "two", "three"}

    assert failure_recall({"one", "two", "three"}, expected) == 1.0
    assert failure_recall({"one", "two"}, expected) == 2 / 3


def test_dag_existence_rejects_hallucinated_or_stale_dags() -> None:
    inventory = {"clients_data", "event_bus_to_payloads_historical"}
    half_exist = 1 / 2

    assert dag_existence_rate({"clients_data"}, inventory) == 1.0
    assert dag_existence_rate({"clients_data", "missing_dag"}, inventory) == half_exist
    assert dag_existence_rate(set(), inventory) == 1.0


def test_regional_count_accuracy_requires_exact_counts() -> None:
    expected = {"US-01": 78, "CA-02": 6}
    one_of_two_regions = 1 / 2

    assert regional_count_accuracy(expected, expected) == 1.0
    assert (
        regional_count_accuracy({"US-01": 78, "CA-02": 5}, expected)
        == one_of_two_regions
    )
    assert regional_count_accuracy({"US-01": 78}, expected) == one_of_two_regions
    assert regional_count_accuracy({}, {}) == 1.0


def test_compute_detection_routes_spark_and_batch_jobs() -> None:
    assert detect_compute_kind("{spark_submit.py:807} submit") is ComputeKind.SPARK
    assert detect_compute_kind("python -m pyadapters.batch") is ComputeKind.BATCH
    assert detect_compute_kind("ordinary log") is ComputeKind.UNKNOWN
