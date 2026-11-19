# Databricks notebook source
"""Plot dated KPO/Spark memory evidence and input sizes without changing data."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

# COMMAND ----------

DBUTILS = globals()["dbutils"]
SHOW = globals()["display"]
DBUTILS.widgets.text("observations_json", "[]", "Dated evidence records (JSON)")
DBUTILS.widgets.text("max_files", "10000", "Maximum files per observation")
GIB = 1024**3
MAX_INPUT_PATHS = 100
MAX_OBSERVATIONS = 5000
MIN_COMPARISON_POINTS = 2
BYTE_FIELDS = (
    "input_bytes",
    "memory_request_bytes",
    "memory_limit_bytes",
    "peak_memory_bytes",
)


def require(condition: bool, message: str) -> None:
    """Reject evidence that cannot be compared safely."""
    if not condition:
        raise ValueError(message)


def timestamp(value: str) -> datetime:
    """Parse an explicitly timezone-qualified instant."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None, "Timestamps must include a timezone")
    return parsed.astimezone(UTC)


def measure_paths(row: dict[str, Any], max_files: int) -> None:
    """Measure explicit ADLS paths using metadata only, with a file-count bound."""
    paths = row.get("input_paths", [])
    require(bool(paths), "input_paths are required when input_bytes is missing")
    require(
        len(paths) <= MAX_INPUT_PATHS,
        f"An observation may list at most {MAX_INPUT_PATHS} input paths",
    )
    pending = list(paths)
    visited: set[str] = set()
    files: dict[str, dict[str, Any]] = {}
    while pending:
        path = pending.pop()
        require(
            isinstance(path, str) and path.startswith("abfss://") and "*" not in path,
            "Use exact abfss paths; expand version/date wildcards before measurement",
        )
        if path in visited:
            continue
        visited.add(path)
        require(len(visited) <= max_files, "Directory traversal exceeded max_files")
        for item in DBUTILS.fs.ls(path):
            if item.isDir():
                pending.append(item.path)
            else:
                files[item.path] = {
                    "path": item.path,
                    "bytes": int(item.size),
                    "modified_at": datetime.fromtimestamp(
                        item.modificationTime / 1000, UTC
                    ).isoformat(),
                }
                require(len(files) <= max_files, "File inventory exceeded max_files")
    require(bool(files), "No files found; record unavailable instead of zero")
    row["input_bytes"] = sum(item["bytes"] for item in files.values())
    row["input_files"] = sorted(files.values(), key=lambda item: item["path"])
    row["measured_at"] = datetime.now(UTC).isoformat()
    row["data_basis"] = "retained_files_measured_now"
    row["modified_after_comparison"] = any(
        timestamp(item["modified_at"]) > timestamp(row["comparison_at"])
        for item in files.values()
    )


def profile_peak(row: dict[str, Any]) -> None:
    """Extract sampled usage from an exact watch_kpo_task_memory response."""
    profile = row.get("memory_profile")
    if profile is None:
        return
    for field in ("region", "dag_id", "run_id", "task_id"):
        require(profile.get(field) == row.get(field), f"Profile {field} mismatch")
    scope = row["memory_scope"]
    peaks = []
    limits: set[int] = set()
    samples = 0
    for sample in profile.get("history", []):
        if sample.get("try_number") != row.get("try_number"):
            continue
        pods = sample.get("pods", [])
        if scope != "application_total":
            role = "executor" if scope == "max_executor" else scope
            pods = [pod for pod in pods if pod.get("role") == role]
        if not pods or any(not pod.get("metrics_available") for pod in pods):
            continue
        usages = [pod["memory_bytes"] for pod in pods]
        peaks.append(max(usages) if scope == "max_executor" else sum(usages))
        pod_limits = [pod.get("memory_limit_bytes") for pod in pods]
        if all(value is not None and value > 0 for value in pod_limits):
            limits.add(max(pod_limits) if scope == "max_executor" else sum(pod_limits))
        samples += 1
    row["peak_memory_bytes"] = max(peaks) if peaks else None
    row["memory_sample_count"] = samples
    row["memory_evidence"] = "watch_kpo_task_memory history; sampled maximum"
    if row.get("memory_limit_bytes") is None and len(limits) == 1:
        row["memory_limit_bytes"] = limits.pop()
        row["allocation_basis"] = "runtime_pod"


def normalize(row: dict[str, Any], max_files: int) -> dict[str, Any]:
    """Validate one durable observation, preserving unknown metrics as null."""
    row = dict(row)
    required = (
        "client_id",
        "task_id",
        "comparison_at",
        "input_scope",
        "memory_scope",
        "data_basis",
        "evidence",
    )
    require(all(row.get(key) for key in required), f"Missing one of {required}")
    timestamp(row["comparison_at"])
    require(
        row["memory_scope"] in {"pod", "driver", "max_executor", "application_total"},
        "memory_scope must be pod, driver, max_executor, or application_total",
    )
    if row.get("input_bytes") is None and row.get("input_paths"):
        measure_paths(row, max_files)
    profile_peak(row)
    for key in BYTE_FIELDS:
        value = row.get(key)
        require(
            value is None or (type(value) is int and value >= 0),
            f"{key} must be a nonnegative integer byte count or null",
        )
        row[key] = value
    if row["peak_memory_bytes"] is not None:
        require(bool(row.get("memory_evidence")), "Usage requires memory_evidence")
        require(
            row.get("memory_sample_count", 0) > 0, "Usage requires observed samples"
        )
    if any(row[key] is not None for key in BYTE_FIELDS[1:3]):
        require(
            bool(row.get("allocation_basis")), "Allocation requires allocation_basis"
        )
    return row


def growth(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    """Compare first and last known values without dividing by zero."""
    known = [row for row in rows if row[key] is not None]
    if len(known) < MIN_COMPARISON_POINTS:
        return {"percent": None, "reason": "fewer than two observations"}
    first, last = known[0], known[-1]
    baseline = first[key]
    return {
        "from": first["comparison_at"],
        "to": last["comparison_at"],
        "from_bytes": baseline,
        "to_bytes": last[key],
        "percent": (last[key] / baseline - 1) * 100 if baseline else None,
    }


def plot_group(rows: list[dict[str, Any]], title: str) -> dict[str, Any]:
    """Show input bytes and observed/configured memory on separate aligned axes."""
    rows.sort(key=lambda row: timestamp(row["comparison_at"]))
    dates = [timestamp(row["comparison_at"]) for row in rows]
    figure, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    series = [
        (axes[0], "input_bytes", "Input data"),
        (axes[1], "peak_memory_bytes", "Observed sampled peak"),
        (axes[1], "memory_request_bytes", "Configured request"),
        (axes[1], "memory_limit_bytes", "Configured limit"),
    ]
    for axis, key, label in series:
        values = [
            row[key] / GIB if row[key] is not None else float("nan") for row in rows
        ]
        if any(row[key] is not None for row in rows):
            axis.plot(dates, values, marker="o", label=label)
    for axis, label in zip(axes, ["Data size (GiB)", "Memory (GiB)"], strict=True):
        axis.set_ylabel(label)
        axis.grid(alpha=0.25)
        if axis.lines:
            axis.legend(loc="best")
        else:
            axis.text(
                0.5,
                0.5,
                "No captured measurements",
                ha="center",
                transform=axis.transAxes,
            )
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d", tz=UTC))
    if not any(row["peak_memory_bytes"] is not None for row in rows):
        axes[1].text(
            0.02,
            0.95,
            "Observed usage unavailable",
            va="top",
            transform=axes[1].transAxes,
        )
    axes[1].set_xlabel("Comparison date (UTC); source data dates remain in evidence")
    figure.suptitle(title, fontsize=10, wrap=True)
    figure.autofmt_xdate()
    figure.tight_layout()
    SHOW(figure)
    plt.close(figure)
    return {key: growth(rows, key) for key in BYTE_FIELDS}


def main() -> None:
    """Measure optional explicit paths, plot comparable evidence, and return JSON."""
    max_files = int(DBUTILS.widgets.get("max_files"))
    require(max_files > 0, "max_files must be positive")
    inputs = json.loads(DBUTILS.widgets.get("observations_json"))
    require(
        isinstance(inputs, list) and 0 < len(inputs) <= MAX_OBSERVATIONS,
        f"Supply 1-{MAX_OBSERVATIONS} observations",
    )
    rows = [normalize(row, max_files) for row in inputs]
    identities = [
        tuple(
            row.get(key)
            for key in (
                "client_id",
                "region",
                "dag_id",
                "task_id",
                "run_id",
                "try_number",
                "comparison_at",
                "input_scope",
                "memory_scope",
                "allocation_basis",
            )
        )
        for row in rows
    ]
    require(len(identities) == len(set(identities)), "Duplicate observation identity")
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = tuple(
            row.get(field, "")
            for field in (
                "client_id",
                "task_id",
                "input_scope",
                "memory_scope",
                "allocation_basis",
            )
        )
        groups[key].append(row)
    summaries = []
    for key, group in sorted(groups.items()):
        title = " | ".join(part for part in key if part)
        summaries.append({"series": list(key), "growth": plot_group(group, title)})
    result = {"schema_version": 1, "observations": rows, "summaries": summaries}
    DBUTILS.notebook.exit(json.dumps(result, sort_keys=True))


main()
