#!/usr/bin/env python3
"""Read production pod and restart health with kubectl."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

from adapters.airflow.configuration import (
    PRODUCTION_ENVIRONMENTS,
    load_airflow_connection,
)
from adapters.airflow.transport import (
    AirflowRegionConfig,
    UrllibAirflowTransport,
    request_with_transient_retry,
)
from workspaces.data_engineering.workflows.prod_support.models import Region

REGION_CONTEXTS = {
    "US-01": "l3-us01",
    "CA-02": "l3-ca02",
}
CONFIGURATION_PATH = Path(__file__).resolve().parents[1] / "configurations.yaml"
NAMESPACE = "scheduler"
MIN_HEALTHY_DAG_COUNT = 10


class ClusterHealthCommandError(TypeError):
    """Raised when kubectl returns an unexpected payload."""

    @classmethod
    def object_required(cls, resource: str) -> ClusterHealthCommandError:
        """Return an error for a non-object kubectl payload."""
        return cls(f"kubectl {resource} response must be an object")


class ClusterHealthConfigurationError(RuntimeError):
    """Raised when conditional Airflow DAG evidence cannot be collected."""

    @classmethod
    def invalid_dag_response(cls) -> ClusterHealthConfigurationError:
        """Return an error for an invalid Airflow DAG response."""
        return cls("Airflow DAG response is missing total_entries")


def _kubectl(context: str, resource: str) -> dict[str, Any]:
    result = subprocess.run(
        (
            "kubectl",
            "--context",
            context,
            "--namespace",
            NAMESPACE,
            "get",
            resource,
            "--output",
            "json",
        ),
        check=True,
        capture_output=True,
        text=True,
    )
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise ClusterHealthCommandError.object_required(resource)
    return value


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _pod_health(
    payload: dict[str, Any],
    restart_window_start: datetime,
    restart_window_end: datetime,
) -> tuple[bool, int, int, tuple[str, ...]]:
    pods = tuple(
        item
        for item in payload.get("items", ())
        if isinstance(item, dict)
        and item.get("status", {}).get("phase") not in {"Succeeded", "Failed"}
    )
    unready: list[str] = []
    restart_count = 0
    cumulative_restart_count = 0
    for pod in pods:
        metadata = pod.get("metadata", {})
        status = pod.get("status", {})
        statuses = tuple(status.get("containerStatuses") or ())
        cumulative_restart_count += sum(
            int(item.get("restartCount", 0)) for item in statuses
        )
        restart_count += sum(
            1
            for item in statuses
            if (
                (
                    finished_at := _parse_timestamp(
                        item.get("lastState", {})
                        .get("terminated", {})
                        .get("finishedAt")
                    )
                )
                is not None
                and restart_window_start <= finished_at < restart_window_end
            )
        )
        if (
            status.get("phase") != "Running"
            or not statuses
            or not all(item.get("ready") is True for item in statuses)
        ):
            unready.append(str(metadata.get("name", "unknown pod")))
    symptoms = (
        (f"unready pods: {', '.join(unready)}",)
        if unready
        else (f"{len(pods)} active pods are running and ready",)
    )
    return not unready, restart_count, cumulative_restart_count, symptoms


def _active_dag_count(region: str) -> int:
    connection = load_airflow_connection(
        PRODUCTION_ENVIRONMENTS[Region(region)],
        CONFIGURATION_PATH,
    )
    config = AirflowRegionConfig(
        Region(region),
        connection.host,
        connection.username,
        connection.password,
    )
    response = request_with_transient_retry(
        UrllibAirflowTransport(),
        config,
        "GET",
        "/api/v1/dags?limit=1&only_active=true",
    )
    if not isinstance(response, dict) or not isinstance(
        response.get("total_entries"), int
    ):
        raise ClusterHealthConfigurationError.invalid_dag_response()
    return response["total_entries"]


def inspect_region(
    region: str,
    restart_window_start: datetime,
    restart_window_end: datetime,
) -> dict[str, object]:
    """Return one read-only regional cluster-health observation."""
    context = REGION_CONTEXTS[region]
    (
        pods_healthy,
        restart_count,
        cumulative_restart_count,
        symptoms,
    ) = _pod_health(
        _kubectl(context, "pods"),
        restart_window_start,
        restart_window_end,
    )
    active_dag_count: int | None = None
    warnings: list[str] = []
    if not pods_healthy and any("dag-processor" in symptom for symptom in symptoms):
        try:
            active_dag_count = _active_dag_count(region)
            if active_dag_count >= MIN_HEALTHY_DAG_COUNT:
                pods_healthy = True
        except (ClusterHealthConfigurationError, HTTPError, URLError) as error:
            warnings.append(f"DAG count query failed: {error}")
    return {
        "region": region,
        "observed_at": datetime.now(UTC).isoformat(),
        "pods_healthy": pods_healthy,
        "restart_count": restart_count,
        "cumulative_restart_count": cumulative_restart_count,
        "restart_window_start": restart_window_start.isoformat(),
        "restart_window_end": restart_window_end.isoformat(),
        "active_dag_count": active_dag_count,
        "dags_parsing_healthy": (
            active_dag_count >= MIN_HEALTHY_DAG_COUNT
            if active_dag_count is not None
            else None
        ),
        "keda_status": "unknown",
        "symptoms": symptoms,
        "warnings": tuple(warnings),
    }


def main() -> None:
    """Run the selected regional health check and emit JSON."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", choices=tuple(REGION_CONTEXTS), required=True)
    parser.add_argument("--since", type=datetime.fromisoformat, required=True)
    parser.add_argument("--before", type=datetime.fromisoformat, required=True)
    arguments = parser.parse_args()
    if (
        arguments.since.tzinfo is None
        or arguments.before.tzinfo is None
        or arguments.since >= arguments.before
    ):
        parser.error("--since and --before must be timezone-aware and ordered")
    payload = inspect_region(
        arguments.region,
        arguments.since,
        arguments.before,
    )
    sys.stdout.write(f"{json.dumps(payload, sort_keys=True)}\n")


if __name__ == "__main__":
    main()
