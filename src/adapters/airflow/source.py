"""Read-only Airflow REST adapter for production-support evidence."""

from __future__ import annotations

import asyncio
import base64
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from adapters.airflow.retry import AirflowRetryMixin
from workspaces.data_engineering.agents.production_support.models import (
    AirflowFailure,
    Region,
)
from workspaces.data_engineering.agents.production_support.ports import (
    TaskLogUnavailableError,
)
from workspaces.data_engineering.agents.production_support.workloads import (
    AirflowTaskMetadata,
)


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


@dataclass(frozen=True, slots=True)
class AirflowRegionConfig:
    """Connection settings for one Airflow production region."""

    region: Region
    host: str
    username: str
    password: str


class AirflowTransport(Protocol):
    """Small HTTP boundary used by the Airflow source."""

    def request(
        self,
        config: AirflowRegionConfig,
        method: str,
        path: str,
        payload: Mapping[str, object] | None = None,
    ) -> object:
        """Return a decoded JSON object or text response."""


class UrllibAirflowTransport:
    """Airflow transport implemented with the Python standard library."""

    def request(
        self,
        config: AirflowRegionConfig,
        method: str,
        path: str,
        payload: Mapping[str, object] | None = None,
    ) -> object:
        """Execute one authenticated Airflow request."""
        authorization = base64.b64encode(
            f"{config.username}:{config.password}".encode()
        ).decode()
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(
            f"{config.host}{path}",
            data=data,
            headers={
                "Authorization": f"Basic {authorization}",
                "Content-Type": "application/json",
            },
            method=method,
        )
        with urlopen(request, timeout=30) as response:
            content = response.read().decode()
            content_type = response.headers.get_content_type()
        return json.loads(content) if content_type == "application/json" else content


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
    def from_environment(cls) -> AirflowApiSource:
        """Load the production region settings from established variables."""
        values = (
            (
                Region.US_01,
                "https://airflow-us01.precisionlender.com",
                "USAIRFLORUSER",
                "USAIRFLOWPASSWORD",
            ),
            (
                Region.CA_02,
                "https://airflow-ca02.precisionlender.com",
                "CAAIRFLORUSER",
                "CAAIRFLOWPASSWORD",
            ),
        )
        regions = []
        for region, host, username_env, password_env in values:
            username = os.environ.get(username_env)
            password = os.environ.get(password_env)
            if not username or not password:
                message = f"missing {username_env} or {password_env}"
                raise AirflowApiError(message)
            regions.append(AirflowRegionConfig(region, host, username, password))
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
                self._transport.request,
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
            self._transport.request,
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
            response = self._transport.request(
                config,
                "POST",
                "/api/v1/dags/~/dagRuns/~/taskInstances/list",
                payload,
            )
            page, total = _task_instances(response)
            failures.extend(_failure(config.region, item) for item in page)
            if not page or len(failures) >= total:
                return tuple(failures)
            payload["page_offset"] = len(failures)

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
            response = self._transport.request(
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
