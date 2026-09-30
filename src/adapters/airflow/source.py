"""Read-only Airflow REST adapter for production-support evidence."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote

from adapters.airflow import transport as _transport
from adapters.airflow.configuration import (
    PRODUCTION_ENVIRONMENTS,
    load_airflow_connection,
)
from adapters.airflow.retry import AirflowRetryMixin
from adapters.local.configuration import DEFAULT_CONFIGURATION_PATH
from workspaces.data_engineering.workflows.prod_support.models import (
    AirflowFailure,
    Region,
)
from workspaces.data_engineering.workflows.prod_support.ports import (
    TaskLogUnavailableError,
)
from workspaces.data_engineering.workflows.prod_support.workloads import (
    AirflowTaskMetadata,
)

AIRFLOW_503_BACKOFF_SECONDS = _transport.AIRFLOW_503_BACKOFF_SECONDS
AIRFLOW_503_MAX_ATTEMPTS = _transport.AIRFLOW_503_MAX_ATTEMPTS
HTTP_STATUS_BAD_GATEWAY = _transport.HTTP_STATUS_BAD_GATEWAY
HTTP_STATUS_SERVICE_UNAVAILABLE = _transport.HTTP_STATUS_SERVICE_UNAVAILABLE
AirflowRegionConfig = _transport.AirflowRegionConfig
AirflowTransport = _transport.AirflowTransport
UrllibAirflowTransport = _transport.UrllibAirflowTransport
request_with_transient_retry = _transport.request_with_transient_retry


class AirflowApiError(RuntimeError):
    """Raised when Airflow credentials or API responses are invalid."""

    @classmethod
    def invalid_task_metadata(cls) -> AirflowApiError:
        """Return an error for a non-object task response."""
        return cls("Airflow task metadata response must be an object")

    @classmethod
    def missing_operator_name(cls) -> AirflowApiError:
        """Return an error for task metadata without an operator."""
        return cls("Airflow task metadata response is missing operator_name")


class AirflowApiSource(AirflowRetryMixin):
    """Discover failures, exact logs, and bounded same-task successes."""

    _transport: AirflowTransport

    def __init__(
        self,
        regions: tuple[AirflowRegionConfig, ...],
        transport: AirflowTransport | None = None,
    ) -> None:
        """Initialize the source with explicit region credentials."""
        self._regions = regions
        self._transport = transport or UrllibAirflowTransport()

    @classmethod
    def from_configuration(
        cls,
        path: Path = DEFAULT_CONFIGURATION_PATH,
    ) -> AirflowApiSource:
        """Load produs and prodca connections named in configurations.yaml."""
        regions = []
        for region, environment in PRODUCTION_ENVIRONMENTS.items():
            connection = load_airflow_connection(environment, path)
            regions.append(
                AirflowRegionConfig(
                    region,
                    connection.host,
                    connection.username,
                    connection.password,
                )
            )
        return cls(tuple(regions))

    async def discover_failures(self, since: datetime) -> tuple[AirflowFailure, ...]:
        """Query failures by end date across all configured regions."""
        batches = await asyncio.gather(
            *(
                self.discover_region_failures(config.region, since)
                for config in self._regions
            )
        )
        return tuple(item for batch in batches for item in batch)

    async def discover_region_failures(
        self,
        region: Region,
        since: datetime,
    ) -> tuple[AirflowFailure, ...]:
        """Query one explicitly selected production region."""
        return await asyncio.to_thread(
            self._discover_region,
            self._config_for(region),
            since,
        )

    async def fetch_log(self, failure: AirflowFailure) -> str:
        """Retrieve the exact task log for the recorded attempt."""
        config = next(
            (item for item in self._regions if item.region is failure.region),
            None,
        )
        if config is None:
            message = f"region is not configured: {failure.region}"
            raise AirflowApiError(message)
        path = "/api/v1/" + "/".join(
            quote(part, safe="")
            for part in (
                "dags",
                failure.dag_id,
                "dagRuns",
                failure.run_id,
                "taskInstances",
                failure.task_id,
                "logs",
                str(failure.try_number),
            )
        )
        try:
            response = await asyncio.to_thread(
                request_with_transient_retry,
                self._transport,
                config,
                "GET",
                path,
            )
        except HTTPError as error:
            raise TaskLogUnavailableError(
                failure.failure_id,
                error.code,
            ) from error
        if isinstance(response, str):
            return response
        if isinstance(response, dict):
            content = response.get("content")
            if isinstance(content, str):
                return content
        message = "Airflow task log response must contain text content"
        raise AirflowApiError(message)

    async def has_success_within(
        self,
        failure: AirflowFailure,
        start_at: datetime,
        end_at: datetime,
    ) -> bool:
        """Return whether the same DAG and task succeeded in the window."""
        if start_at.tzinfo is None or end_at.tzinfo is None:
            message = "Airflow success window must be timezone-aware"
            raise ValueError(message)
        if end_at <= start_at:
            message = "Airflow success window end must be later than its start"
            raise ValueError(message)
        return await asyncio.to_thread(
            self._has_success_within,
            self._config_for(failure.region),
            failure,
            start_at,
            end_at,
        )

    async def fetch_task_metadata(
        self,
        failure: AirflowFailure,
    ) -> AirflowTaskMetadata:
        """Retrieve operator metadata for deterministic workload routing."""
        config = self._config_for(failure.region)
        path = "/api/v1/" + "/".join(
            quote(part, safe="")
            for part in ("dags", failure.dag_id, "tasks", failure.task_id)
        )
        response = await asyncio.to_thread(
            request_with_transient_retry,
            self._transport,
            config,
            "GET",
            path,
        )
        if not isinstance(response, dict):
            raise AirflowApiError.invalid_task_metadata()
        operator_name = response.get("operator_name")
        class_ref = response.get("class_ref")
        if not isinstance(operator_name, str) and isinstance(class_ref, dict):
            operator_name = class_ref.get("class_name")
        if not isinstance(operator_name, str) or not operator_name.strip():
            raise AirflowApiError.missing_operator_name()
        return AirflowTaskMetadata(
            dag_id=failure.dag_id,
            task_id=failure.task_id,
            operator_name=operator_name,
        )

    def _discover_region(
        self,
        config: AirflowRegionConfig,
        since: datetime,
    ) -> tuple[AirflowFailure, ...]:
        if since.tzinfo is None:
            message = "Airflow discovery cutoff must be timezone-aware"
            raise ValueError(message)
        payload: dict[str, object] = {
            "state": ["failed"],
            "end_date_gte": since.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "page_limit": 1000,
            "page_offset": 0,
        }
        failures: list[AirflowFailure] = []
        while True:
            response = self._discover_request(config, payload)
            page, total = _task_instances(response)
            failures.extend(_failure(config.region, item) for item in page)
            if not page or len(failures) >= total:
                return tuple(failures)
            payload["page_offset"] = len(failures)

    def _discover_request(
        self,
        config: AirflowRegionConfig,
        payload: Mapping[str, object],
    ) -> object:
        """Retry transient Airflow gateway and availability errors."""
        return request_with_transient_retry(
            self._transport,
            config,
            "POST",
            "/api/v1/dags/~/dagRuns/~/taskInstances/list",
            payload,
        )

    def _has_success_within(
        self,
        config: AirflowRegionConfig,
        failure: AirflowFailure,
        start_at: datetime,
        end_at: datetime,
    ) -> bool:
        """Query exact same-task successes and enforce the half-open window."""
        payload: dict[str, object] = {
            "dag_ids": [failure.dag_id],
            "task_ids": [failure.task_id],
            "state": ["success"],
            "end_date_gte": start_at.astimezone(UTC)
            .isoformat()
            .replace(
                "+00:00",
                "Z",
            ),
            "end_date_lte": end_at.astimezone(UTC)
            .isoformat()
            .replace(
                "+00:00",
                "Z",
            ),
            "page_limit": 100,
            "page_offset": 0,
        }
        page_offset = 0
        while True:
            response = request_with_transient_retry(
                self._transport,
                config,
                "POST",
                "/api/v1/dags/~/dagRuns/~/taskInstances/list",
                payload,
            )
            page, total = _task_instances(response)
            if any(
                str(item.get("dag_id")) == failure.dag_id
                and str(item.get("task_id")) == failure.task_id
                and start_at <= _end_at(item) < end_at
                for item in page
                if item.get("end_date") is not None
            ):
                return True
            page_offset += len(page)
            if not page or page_offset >= total:
                return False
            payload["page_offset"] = page_offset

    def _config_for(self, region: Region) -> AirflowRegionConfig:
        config = next((item for item in self._regions if item.region is region), None)
        if config is None:
            message = f"region is not configured: {region}"
            raise AirflowApiError(message)
        return config


def _task_instances(response: object) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(response, dict):
        message = "Airflow discovery response must be an object"
        raise AirflowApiError(message)
    items = response.get("task_instances")
    total = response.get("total_entries")
    if not isinstance(items, list) or not isinstance(total, int):
        message = "Airflow discovery response is missing task instances"
        raise AirflowApiError(message)
    return [item for item in items if isinstance(item, dict)], total


def _failure(region: Region, value: dict[str, Any]) -> AirflowFailure:
    end_at = _end_at(value)
    raw_start = value.get("start_date")
    start_at = (
        datetime.fromisoformat(str(raw_start).replace("Z", "+00:00"))
        if raw_start is not None
        else end_at
    )
    return AirflowFailure(
        region=region,
        dag_id=str(value["dag_id"]),
        run_id=str(value["dag_run_id"]),
        task_id=str(value["task_id"]),
        start_at=start_at,
        end_at=end_at,
        try_number=int(value.get("try_number") or 1),
    )


def _end_at(value: Mapping[str, object]) -> datetime:
    """Parse a task-instance end timestamp."""
    return datetime.fromisoformat(str(value["end_date"]).replace("Z", "+00:00"))
