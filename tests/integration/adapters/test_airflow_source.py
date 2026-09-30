import asyncio
import json
from datetime import UTC, datetime
from urllib.error import HTTPError

import pytest

from adapters.airflow.source import (
    AIRFLOW_503_MAX_ATTEMPTS,
    HTTP_STATUS_BAD_GATEWAY,
    HTTP_STATUS_SERVICE_UNAVAILABLE,
    AirflowApiError,
    AirflowApiSource,
    AirflowRegionConfig,
    UrllibAirflowTransport,
)
from workspaces.data_engineering.workflows.prod_support.models import (
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


@pytest.mark.parametrize(
    ("status_code", "status_text"),
    [
        (HTTP_STATUS_BAD_GATEWAY, "Bad Gateway"),
        (HTTP_STATUS_SERVICE_UNAVAILABLE, "Service Unavailable"),
    ],
)
def test_airflow_source_retries_transient_gateway_errors_three_total_attempts(
    status_code: int,
    status_text: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    sleeps: list[float] = []

    class RetryTransport(FakeTransport):
        def request(
            self,
            config: AirflowRegionConfig,
            method: str,
            path: str,
            payload: dict[str, object] | None = None,
        ) -> object:
            nonlocal attempts
            if method == "POST":
                attempts += 1
                if attempts < AIRFLOW_503_MAX_ATTEMPTS:
                    raise HTTPError(
                        "https://airflow.example.test",
                        status_code,
                        status_text,
                        {},
                        None,
                    )
            return super().request(config, method, path, payload)

    monkeypatch.setattr("adapters.airflow.transport.time.sleep", sleeps.append)
    source = AirflowApiSource(
        (
            AirflowRegionConfig(
                Region.US_01,
                "https://airflow.example.test",
                "user",
                "password",
            ),
        ),
        RetryTransport(),
    )

    failures = asyncio.run(
        source.discover_failures(datetime(2026, 9, 25, 5, tzinfo=UTC))
    )

    assert len(failures) == 1
    assert attempts == AIRFLOW_503_MAX_ATTEMPTS
    assert sleeps == [30.0, 30.0]


def test_airflow_source_reads_structured_log_content() -> None:
    class StructuredLogTransport(FakeTransport):
        def request(
            self,
            config: AirflowRegionConfig,
            method: str,
            path: str,
            payload: dict[str, object] | None = None,
        ) -> object:
            if method == "GET":
                return {"content": "structured task log"}
            return super().request(config, method, path, payload)

    source = AirflowApiSource(
        (
            AirflowRegionConfig(
                Region.US_01,
                "https://airflow.example.test",
                "user",
                "password",
            ),
        ),
        StructuredLogTransport(),
    )
    failure = AirflowFailure(
        Region.US_01,
        "dag",
        "run",
        "task",
        datetime(2026, 9, 25, 5, tzinfo=UTC),
        datetime(2026, 9, 25, 6, tzinfo=UTC),
    )

    assert asyncio.run(source.fetch_log(failure)) == "structured task log"


def test_airflow_source_checks_same_task_success_inside_window() -> None:
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
    failure = AirflowFailure(
        Region.US_01,
        "l3-main-client",
        "run",
        "high_quality_accounts",
        datetime(2026, 9, 25, 5, tzinfo=UTC),
        datetime(2026, 9, 25, 6, tzinfo=UTC),
    )

    recovered = asyncio.run(
        source.has_success_within(
            failure,
            datetime(2026, 9, 25, 5, tzinfo=UTC),
            datetime(2026, 9, 26, 5, tzinfo=UTC),
        )
    )

    assert recovered is True
    assert transport.payload["state"] == ["success"]
    assert transport.payload["dag_ids"] == ["l3-main-client"]
    assert transport.payload["task_ids"] == ["high_quality_accounts"]


def test_airflow_source_reads_task_operator_metadata() -> None:
    class MetadataTransport(FakeTransport):
        def request(
            self,
            config: AirflowRegionConfig,
            method: str,
            path: str,
            payload: dict[str, object] | None = None,
        ) -> object:
            del config, payload
            assert method == "GET"
            assert path == "/api/v1/dags/dag/tasks/task"
            return {"class_ref": {"class_name": "SparkSubmitOperator"}}

    source = AirflowApiSource(
        (
            AirflowRegionConfig(
                Region.US_01,
                "https://airflow.example.test",
                "user",
                "password",
            ),
        ),
        MetadataTransport(),
    )
    failure = AirflowFailure(
        Region.US_01,
        "dag",
        "run",
        "task",
        datetime(2026, 9, 25, 5, tzinfo=UTC),
        datetime(2026, 9, 25, 6, tzinfo=UTC),
    )

    metadata = asyncio.run(source.fetch_task_metadata(failure))

    assert metadata.operator_name == "SparkSubmitOperator"


def test_airflow_source_preserves_failure_without_start_date() -> None:
    class MissingStartTransport(FakeTransport):
        def request(
            self,
            config: AirflowRegionConfig,
            method: str,
            path: str,
            payload: dict[str, object] | None = None,
        ) -> object:
            del config, method, path, payload
            return {
                "task_instances": [
                    {
                        "dag_id": "dag",
                        "dag_run_id": "run",
                        "task_id": "task",
                        "start_date": None,
                        "end_date": "2026-09-25T06:00:00Z",
                        "try_number": 1,
                    }
                ],
                "total_entries": 1,
            }

    source = AirflowApiSource(
        (
            AirflowRegionConfig(
                Region.CA_02,
                "https://airflow.example.test",
                "user",
                "password",
            ),
        ),
        MissingStartTransport(),
    )

    failure = asyncio.run(
        source.discover_failures(datetime(2026, 9, 25, 5, tzinfo=UTC))
    )[0]

    assert failure.start_at == failure.end_at


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
        "adapters.airflow.transport.urlopen",
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
