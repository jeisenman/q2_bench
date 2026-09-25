from datetime import date

from workspaces.data_engineering.agents.prod_support import airflow_failure_url
from workspaces.data_engineering.agents.prod_support.models import Region
from workspaces.data_engineering.benchmarks import (
    ComputeKind,
    TaskObservation,
    detect_compute_kind,
    failure_recall,
    filter_failures,
)


def test_airflow_links_filter_each_region_at_operational_cutoff() -> None:
    operational_date = date(2026, 9, 24)

    us_url = airflow_failure_url(Region.US_01, operational_date)
    ca_url = airflow_failure_url(Region.CA_02, operational_date)

    assert "airflow-us01.precisionlender.com" in us_url
    assert "airflow-ca02.precisionlender.com" in ca_url
    assert "_flt_3_state=failed" in us_url
    assert "_flt_2_end_date=09%2F24%2F2026+5%3A00+AM" in us_url


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


def test_compute_detection_routes_spark_and_batch_jobs() -> None:
    assert detect_compute_kind("{spark_submit.py:807} submit") is ComputeKind.SPARK
    assert detect_compute_kind("python -m pyadapters.batch") is ComputeKind.BATCH
    assert detect_compute_kind("ordinary log") is ComputeKind.UNKNOWN
