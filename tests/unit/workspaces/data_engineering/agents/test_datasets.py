import asyncio
import json
from datetime import UTC, date, datetime

import pytest

from workspaces.data_engineering.agents.production_support import AirflowFailure
from workspaces.data_engineering.agents.production_support.datasets import (
    ReplayAirflowFailureSource,
    capture_day,
)
from workspaces.data_engineering.agents.production_support.models import Region


class FakeSource:
    async def discover_failures(self, since: datetime) -> tuple[AirflowFailure, ...]:
        del since
        return (
            AirflowFailure(
                Region.CA_02,
                "dag",
                "run",
                "task",
                datetime(2026, 9, 24, 5, tzinfo=UTC),
                datetime(2026, 9, 24, 6, tzinfo=UTC),
            ),
        )

    async def fetch_log(self, failure: AirflowFailure) -> str:
        del failure
        return "Authorization: Bearer abc password=unsafe OOMKilled"


class RegionalFakeSource:
    def __init__(self) -> None:
        self.regions: list[Region] = []
        self.fetched: list[str] = []

    async def discover_failures(
        self,
        since: datetime,
    ) -> tuple[AirflowFailure, ...]:
        del since
        raise AssertionError

    async def discover_region_failures(
        self,
        region: Region,
        since: datetime,
    ) -> tuple[AirflowFailure, ...]:
        assert since == datetime(2026, 9, 24, 5, tzinfo=UTC)
        self.regions.append(region)
        return (
            AirflowFailure(
                region,
                f"delivery_to_promise-{region.value}",
                "run-d2p",
                "delivery_to_promise",
                datetime(2026, 9, 25, 5, tzinfo=UTC),
                datetime(2026, 9, 25, 6, tzinfo=UTC),
            ),
            AirflowFailure(
                region,
                f"ordinary-{region.value}",
                "run-ordinary",
                "ordinary_task",
                datetime(2026, 9, 25, 6, tzinfo=UTC),
                datetime(2026, 9, 25, 7, tzinfo=UTC),
            ),
        )

    async def fetch_log(self, failure: AirflowFailure) -> str:
        self.fetched.append(failure.task_id)
        return "terminal failure"

    async def has_success_within(
        self,
        failure: AirflowFailure,
        start_at: datetime,
        end_at: datetime,
    ) -> bool:
        assert start_at == datetime(2026, 9, 25, 5, tzinfo=UTC)
        assert end_at == datetime(2026, 9, 26, 5, tzinfo=UTC)
        return failure.task_id == "delivery_to_promise"


def test_capture_and_replay_redacted_airflow_evidence(tmp_path) -> None:
    target = asyncio.run(capture_day(FakeSource(), date(2026, 9, 24), tmp_path))
    content = target.read_text(encoding="utf-8")
    replay = ReplayAirflowFailureSource(target)
    failures = asyncio.run(
        replay.discover_failures(datetime(2026, 9, 24, 5, tzinfo=UTC))
    )

    assert "abc" not in content
    assert "unsafe" not in content
    assert failures[0].log.endswith("OOMKilled")


def test_capture_reads_omission_logs_and_verifies_recovery(tmp_path) -> None:
    source = RegionalFakeSource()

    target = asyncio.run(
        capture_day(
            source,
            date(2026, 9, 25),
            tmp_path,
            regions=(Region.CA_02,),
        )
    )
    captured = json.loads(target.read_text(encoding="utf-8"))

    assert source.regions == [Region.CA_02]
    assert source.fetched == ["delivery_to_promise", "ordinary_task"]
    assert captured["regions"] == ["CA-02"]
    omitted, investigated = captured["records"]
    assert omitted["triage_status"] == "omitted"
    assert omitted["log_retrieval"] == "exact_task_attempt"
    assert omitted["omission_code"] == "D2P"
    assert omitted["log"] == "terminal failure"
    assert omitted["success_within_window"] is True
    assert investigated["triage_status"] == "investigated"


def test_capture_rejects_invalid_region_scope(tmp_path) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        asyncio.run(
            capture_day(
                FakeSource(),
                date(2026, 9, 25),
                tmp_path,
                regions=(),
            )
        )


def test_replay_rejects_non_list_records(tmp_path) -> None:
    dataset = tmp_path / "invalid.json"
    dataset.write_text(json.dumps({"records": {}}), encoding="utf-8")

    with pytest.raises(TypeError, match="records must be a list"):
        ReplayAirflowFailureSource(dataset)


def test_replay_rejects_non_mapping_record(tmp_path) -> None:
    dataset = tmp_path / "invalid.json"
    dataset.write_text(json.dumps({"records": ["invalid"]}), encoding="utf-8")

    with pytest.raises(TypeError, match="record must be an object"):
        ReplayAirflowFailureSource(dataset)
