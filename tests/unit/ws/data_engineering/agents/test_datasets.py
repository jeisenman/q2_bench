import asyncio
import json
from datetime import UTC, date, datetime

import pytest

from agentsdk.ws.data_engineering.agents.prod_support import AirflowFailure
from agentsdk.ws.data_engineering.agents.prod_support.datasets import (
    ReplayAirflowFailureSource,
    capture_day,
)
from agentsdk.ws.data_engineering.agents.prod_support.models import Region


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
