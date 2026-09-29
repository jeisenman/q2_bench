"""Authenticated Airflow HTTP transport with transient-error retries."""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from workspaces.data_engineering.workflows.prod_support.models import Region

HTTP_STATUS_BAD_GATEWAY = 502
HTTP_STATUS_SERVICE_UNAVAILABLE = 503
AIRFLOW_TRANSIENT_STATUS_CODES = frozenset(
    {HTTP_STATUS_BAD_GATEWAY, HTTP_STATUS_SERVICE_UNAVAILABLE}
)
AIRFLOW_TRANSIENT_MAX_ATTEMPTS = 3
AIRFLOW_TRANSIENT_BACKOFF_SECONDS = 30.0
# Backward-compatible names for callers that specifically reference 503 handling.
AIRFLOW_503_MAX_ATTEMPTS = AIRFLOW_TRANSIENT_MAX_ATTEMPTS
AIRFLOW_503_BACKOFF_SECONDS = AIRFLOW_TRANSIENT_BACKOFF_SECONDS


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


def request_with_transient_retry(
    transport: AirflowTransport,
    config: AirflowRegionConfig,
    method: str,
    path: str,
    payload: Mapping[str, object] | None = None,
) -> object:
    """Retry HTTP 502 and 503 responses three times with 30-second backoff."""
    for attempt in range(AIRFLOW_TRANSIENT_MAX_ATTEMPTS):
        try:
            return transport.request(config, method, path, payload)
        except HTTPError as error:
            if (
                error.code not in AIRFLOW_TRANSIENT_STATUS_CODES
                or attempt == AIRFLOW_TRANSIENT_MAX_ATTEMPTS - 1
            ):
                raise
            time.sleep(AIRFLOW_TRANSIENT_BACKOFF_SECONDS)
    raise AssertionError
