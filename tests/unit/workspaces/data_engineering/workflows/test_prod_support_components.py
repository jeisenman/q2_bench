"""Focused tests for production-support orchestration components."""

import asyncio
from datetime import UTC, date, datetime

import pytest

from workspaces.data_engineering.workflows.prod_support import (
    AirflowCheckConfigurationError,
    AirflowChecker,
    AirflowFailure,
    ClusterChecker,
    DataInternalReporter,
    DeveloperReporter,
    FailureDiagnosis,
    FollowUp,
    Region,
    ReportFindings,
)
from workspaces.data_engineering.workflows.prod_support.cluster_health import (
    RegionalClusterHealth,
)
from workspaces.data_engineering.workflows.prod_support.models import FailureKind
from workspaces.data_engineering.workflows.prod_support.reporting import (
    ProdSupportReportContext,
    format_reports_with_context,
)

EXPECTED_REGION_COUNT = 2


class FakeAirflowSource:
    """Return deterministic discovery records for checker tests."""

    def __init__(self, failures: tuple[AirflowFailure, ...]) -> None:
        self.failures = failures

    async def discover_failures(self, since: datetime) -> tuple[AirflowFailure, ...]:
        del since
        return self.failures

    async def fetch_log(self, failure: AirflowFailure) -> str:
        return failure.log


class ConcurrentHealthSource:
    """Require both regional reads to start before either can finish."""

    def __init__(self) -> None:
        self.started: set[Region] = set()
        self.both_started = asyncio.Event()

    async def inspect_health(
        self,
        region: Region,
        restart_window_start: datetime,
        restart_window_end: datetime,
    ) -> RegionalClusterHealth:
        del restart_window_start, restart_window_end
        self.started.add(region)
        if len(self.started) == EXPECTED_REGION_COUNT:
            self.both_started.set()
        await self.both_started.wait()
        return RegionalClusterHealth(region=region, application_healthy=True)


class ConcurrentRegionalAirflowSource(FakeAirflowSource):
    """Require selected regional discoveries to overlap."""

    def __init__(self, failures: tuple[AirflowFailure, ...]) -> None:
        super().__init__(failures)
        self.started: set[Region] = set()
        self.expected: set[Region] = {Region.US_01, Region.CA_02}
        self.all_started = asyncio.Event()

    async def discover_region_failures(
        self,
        region: Region,
        since: datetime,
    ) -> tuple[AirflowFailure, ...]:
        del since
        self.started.add(region)
        if self.started == self.expected:
            self.all_started.set()
        await self.all_started.wait()
        return tuple(item for item in self.failures if item.region is region)


class RecordingHealthSource:
    """Record selected cluster-health calls."""

    def __init__(self) -> None:
        self.started: list[Region] = []

    async def inspect_health(
        self,
        region: Region,
        restart_window_start: datetime,
        restart_window_end: datetime,
    ) -> RegionalClusterHealth:
        del restart_window_start, restart_window_end
        self.started.append(region)
        return RegionalClusterHealth(region=region, application_healthy=True)


def _failure(
    region: Region,
    *,
    day: int = 25,
    task_id: str = "relationship_signals",
) -> AirflowFailure:
    return AirflowFailure(
        region=region,
        dag_id=f"dag-{region.value}",
        run_id=f"run-{day}",
        task_id=task_id,
        start_at=datetime(2026, 9, day, 5, tzinfo=UTC),
        end_at=datetime(2026, 9, day, 6, tzinfo=UTC),
    )


def _diagnosis(failure: AirflowFailure) -> FailureDiagnosis:
    return FailureDiagnosis(
        failure_id=failure.failure_id,
        kind=FailureKind.APPLICATION_ERROR,
        confidence="confirmed",
        evidence=("terminal error",),
    )


def test_airflow_checker_filters_region_window_and_duplicates() -> None:
    ca_failure = _failure(Region.CA_02)
    checker = AirflowChecker(
        FakeAirflowSource(
            (
                _failure(Region.US_01),
                _failure(Region.CA_02, day=24),
                ca_failure,
                ca_failure,
            )
        ),
        regions=(Region.CA_02,),
    )

    failures = asyncio.run(
        checker.check(
            datetime(2026, 9, 25, 5, tzinfo=UTC),
            datetime(2026, 9, 26, 5, tzinfo=UTC),
        )
    )

    assert failures == (ca_failure,)


def test_airflow_checker_rejects_invalid_boundaries() -> None:
    checker = AirflowChecker(FakeAirflowSource(()))
    boundary = datetime(2026, 9, 25, 5, tzinfo=UTC)

    with pytest.raises(AirflowCheckConfigurationError, match="later than"):
        asyncio.run(checker.check(boundary, boundary))
    with pytest.raises(AirflowCheckConfigurationError, match="timezone-aware"):
        asyncio.run(
            checker.check(
                datetime(2026, 9, 25, 5),
                datetime(2026, 9, 26, 5),
            )
        )
    with pytest.raises(AirflowCheckConfigurationError, match="at least one region"):
        AirflowChecker(FakeAirflowSource(()), regions=())


def test_cluster_checker_reads_both_regions_concurrently() -> None:
    source = ConcurrentHealthSource()

    observations = asyncio.run(
        asyncio.wait_for(
            ClusterChecker(source).check(
                restart_window_start=datetime(2026, 9, 25, 5, tzinfo=UTC),
                restart_window_end=datetime(2026, 9, 26, 5, tzinfo=UTC),
            ),
            timeout=1,
        )
    )

    assert tuple(item.region for item in observations) == (
        Region.US_01,
        Region.CA_02,
    )


def test_cluster_checker_honors_single_region_scope() -> None:
    source = RecordingHealthSource()

    observations = asyncio.run(
        ClusterChecker(source).check(
            (Region.US_01,),
            restart_window_start=datetime(2026, 9, 25, 5, tzinfo=UTC),
            restart_window_end=datetime(2026, 9, 26, 5, tzinfo=UTC),
        )
    )

    assert tuple(item.region for item in observations) == (Region.US_01,)
    assert source.started == [Region.US_01]


def test_airflow_checker_reads_selected_regions_concurrently() -> None:
    source = ConcurrentRegionalAirflowSource(
        (_failure(Region.US_01), _failure(Region.CA_02))
    )

    failures = asyncio.run(
        asyncio.wait_for(
            AirflowChecker(source).check(
                datetime(2026, 9, 25, 5, tzinfo=UTC),
                datetime(2026, 9, 26, 5, tzinfo=UTC),
            ),
            timeout=1,
        )
    )

    assert len(failures) == EXPECTED_REGION_COUNT
    assert source.started == {Region.US_01, Region.CA_02}


def test_audience_reporters_match_assembled_report_contract() -> None:
    failure = _failure(Region.US_01)
    diagnosis = _diagnosis(failure)
    context = ProdSupportReportContext()
    findings = ReportFindings((failure,), (diagnosis,))
    reports = format_reports_with_context(
        date(2026, 9, 25),
        (failure,),
        (diagnosis,),
        context=context,
    )

    assert DeveloperReporter().render(findings) == reports.developer
    assert (
        DataInternalReporter().render(
            date(2026, 9, 25),
            findings,
        )
        == reports.data_internal
    )
    assert (
        FollowUp().render(
            date(2026, 9, 25),
            findings,
        )
        == reports.follow_up
    )
