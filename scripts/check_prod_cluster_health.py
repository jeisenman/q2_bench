#!/usr/bin/env python3
"""Read production pod, restart, and KEDA health with kubectl."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from typing import Any

REGION_CONTEXTS = {
    "US-01": "l3-us01",
    "CA-02": "l3-ca02",
}
NAMESPACE = "scheduler"


class ClusterHealthCommandError(TypeError):
    """Raised when kubectl returns an unexpected payload."""

    @classmethod
    def object_required(cls, resource: str) -> ClusterHealthCommandError:
        """Return an error for a non-object kubectl payload."""
        return cls(f"kubectl {resource} response must be an object")


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


def _keda_health(payload: dict[str, Any]) -> str:
    items = tuple(item for item in payload.get("items", ()) if isinstance(item, dict))
    if not items:
        return "not_configured"
    ready_values = [
        condition.get("status")
        for item in items
        for condition in item.get("status", {}).get("conditions", ())
        if condition.get("type") == "Ready"
    ]
    if ready_values and all(value == "True" for value in ready_values):
        return "healthy"
    if any(value == "False" for value in ready_values):
        return "unhealthy"
    return "unknown"


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
    warnings: tuple[str, ...] = ()
    try:
        keda_status = _keda_health(_kubectl(context, "scaledobjects.keda.sh"))
    except subprocess.CalledProcessError as error:
        keda_status = "unavailable"
        warnings = (f"KEDA query failed with exit code {error.returncode}",)
    return {
        "region": region,
        "observed_at": datetime.now(UTC).isoformat(),
        "pods_healthy": pods_healthy,
        "restart_count": restart_count,
        "cumulative_restart_count": cumulative_restart_count,
        "restart_window_start": restart_window_start.isoformat(),
        "restart_window_end": restart_window_end.isoformat(),
        "keda_status": keda_status,
        "symptoms": symptoms,
        "warnings": warnings,
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
