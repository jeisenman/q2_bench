import asyncio
import json
from datetime import UTC, datetime

import pytest

from agentsdk.adapters.airflow.source import (
    AirflowApiError,
    AirflowApiSource,
    AirflowRegionConfig,
    UrllibAirflowTransport,
)
from agentsdk.ws.data_engineering.agents.prod_support.models import (
    AirflowFailure,
    Region,
)


class FakeTransport:
    def __init__(self) -> None:
        self.payload: dict[str, object] = {}

    def request(
        self,
        config: AirflowRegionConfig,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> object:
        del config
        if method == "GET":
            assert "/logs/1" in path
            return "OOMKilled"
        self.payload = dict(payload or {})
        return {
            "task_instances": [
                {
                    "dag_id": "l3-main-client",
                    "dag_run_id": "scheduled__2026-09-25",
                    "task_id": "high_quality_accounts",
                    "start_date": "2026-09-25T05:00:00Z",
                    "end_date": "2026-09-25T06:00:00Z",
                    "try_number": 1,
                }
            ],
            "total_entries": 1,
        }


def test_airflow_source_discovers_by_end_date_and_fetches_log() -> None:
    transport = FakeTransport()
    source = AirflowApiSource(
        (
            AirflowRegionConfig(
                Region.US_01,
                "https://airflow.example.test",
                "user",
                "password",
            ),
        ),
        transport,
    )
    cutoff = datetime(2026, 9, 25, 5, tzinfo=UTC)

    failures = asyncio.run(source.discover_failures(cutoff))
    log = asyncio.run(source.fetch_log(failures[0]))

    assert transport.payload["end_date_gte"] == "2026-09-25T05:00:00Z"
    assert failures[0].task_id == "high_quality_accounts"
    assert log == "OOMKilled"


def test_airflow_source_builds_regions_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("USAIRFLORUSER", "us-user")
    monkeypatch.setenv("USAIRFLOWPASSWORD", "us-password")
    monkeypatch.setenv("CAAIRFLORUSER", "ca-user")
    monkeypatch.setenv("CAAIRFLOWPASSWORD", "ca-password")

    source = AirflowApiSource.from_environment()

    assert tuple(config.region for config in source._regions) == (
        Region.US_01,
        Region.CA_02,
    )


def test_airflow_source_rejects_missing_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for variable in (
        "USAIRFLORUSER",
        "USAIRFLOWPASSWORD",
        "CAAIRFLORUSER",
        "CAAIRFLOWPASSWORD",
    ):
        monkeypatch.delenv(variable, raising=False)

    with pytest.raises(AirflowApiError, match="missing USAIRFLORUSER"):
        AirflowApiSource.from_environment()


def test_airflow_source_rejects_naive_cutoff() -> None:
    source = AirflowApiSource(
        (
            AirflowRegionConfig(
                Region.US_01,
                "https://airflow.example.test",
                "user",
                "password",
            ),
        ),
        FakeTransport(),
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        asyncio.run(source.discover_failures(datetime(2026, 9, 25, 5)))


def test_airflow_source_rejects_unconfigured_failure_region() -> None:
    source = AirflowApiSource((), FakeTransport())
    failure = AirflowFailure(
        Region.US_01,
        "dag",
        "run",
        "task",
        datetime(2026, 9, 25, 5, tzinfo=UTC),
        datetime(2026, 9, 25, 6, tzinfo=UTC),
    )

    with pytest.raises(AirflowApiError, match="region is not configured"):
        asyncio.run(source.fetch_log(failure))


def test_urllib_transport_decodes_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeHeaders:
        @staticmethod
        def get_content_type() -> str:
            return "application/json"

    class FakeResponse:
        headers = FakeHeaders()

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        @staticmethod
        def read() -> bytes:
            return json.dumps({"task_instances": []}).encode()

    def fake_urlopen(*_args: object, **_kwargs: object) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr(
        "agentsdk.adapters.airflow.source.urlopen",
        fake_urlopen,
    )
    config = AirflowRegionConfig(
        Region.US_01,
        "https://airflow.example.test",
        "user",
        "password",
    )

    result = UrllibAirflowTransport().request(
        config,
        "POST",
        "/api/v1/test",
        {"key": "value"},
    )

    assert result == {"task_instances": []}
