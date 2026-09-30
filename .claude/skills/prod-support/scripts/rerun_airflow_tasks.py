#!/usr/bin/env python3
"""Plan or execute narrowly scoped Airflow task-instance retries."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from airflow_config import AirflowConfigError, find_configuration, load_entry

REGIONS = {"us01": "produs", "ca02": "prodca", "alpha": "alpha", "staging": "staging"}


def load_dotenv(env_file: Path) -> None:
    """Load dotenv values without replacing exported credentials."""
    if not env_file.is_file():
        return
    for raw_line in env_file.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key.isidentifier() or key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def post_json(
    host: str,
    path: str,
    payload: dict[str, Any],
    username: str,
    password: str,
) -> dict[str, Any]:
    """POST JSON to Airflow and return its object response."""
    authorization = base64.b64encode(f"{username}:{password}".encode()).decode()
    request = Request(
        host + path,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Basic {authorization}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
    except HTTPError as error:
        detail = error.read().decode(errors="replace")[:500]
        raise RuntimeError(f"Airflow returned HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise RuntimeError(f"Unable to reach Airflow: {error.reason}") from error
    if not isinstance(result, dict):
        raise RuntimeError("Airflow returned an unexpected response")
    return result


def get_json(
    host: str,
    path: str,
    username: str,
    password: str,
) -> dict[str, Any]:
    """GET JSON from Airflow."""
    authorization = base64.b64encode(f"{username}:{password}".encode()).decode()
    request = Request(
        host + path,
        headers={"Authorization": f"Basic {authorization}"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
    except HTTPError as error:
        detail = error.read().decode(errors="replace")[:500]
        raise RuntimeError(f"Airflow returned HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise RuntimeError(f"Unable to reach Airflow: {error.reason}") from error
    if not isinstance(result, dict):
        raise RuntimeError("Airflow returned an unexpected response")
    return result


def task_references(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract task-instance references from an Airflow clear response."""
    references = result.get("task_instances", [])
    if not isinstance(references, list):
        raise RuntimeError("Airflow returned an invalid task-instance list")
    return [item for item in references if isinstance(item, dict)]


def validate_plan(
    references: list[dict[str, Any]],
    dag_id: str,
    run_id: str,
    task_ids: set[str],
) -> None:
    """Ensure Airflow selected only the requested task instances."""
    if not references:
        raise RuntimeError("Airflow found no matching task instances")
    unexpected = [
        reference
        for reference in references
        if reference.get("dag_id") != dag_id
        or reference.get("dag_run_id") != run_id
        or reference.get("task_id") not in task_ids
    ]
    if unexpected:
        raise RuntimeError(
            "Airflow selected an unexpected task instance: "
            + json.dumps(unexpected[0], sort_keys=True)
        )
    planned_task_ids = {
        reference["task_id"]
        for reference in references
        if isinstance(reference.get("task_id"), str)
    }
    missing = task_ids - planned_task_ids
    if missing:
        raise RuntimeError(
            "Airflow did not select these task IDs: " + ", ".join(sorted(missing))
        )


def build_payload(
    run_id: str,
    task_ids: list[str],
    *,
    dry_run: bool,
    only_failed: bool,
) -> dict[str, Any]:
    """Build a narrowly scoped Airflow clear request."""
    return {
        "dag_run_id": run_id,
        "dry_run": dry_run,
        "include_downstream": True,
        "include_future": False,
        "include_past": False,
        "include_upstream": False,
        "only_failed": only_failed,
        "only_running": False,
        "reset_dag_runs": True,
        "task_ids": task_ids,
    }


def print_references(label: str, references: list[dict[str, Any]]) -> None:
    """Print selected task instances in a stable JSON shape."""
    print(label)
    print(json.dumps({"task_instances": references}, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", choices=sorted(REGIONS), required=True)
    parser.add_argument("--dag-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--task-id", action="append", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--plan-only",
        action="store_true",
        help="Print Airflow's dry-run selection without clearing tasks.",
    )
    mode.add_argument(
        "--execute",
        action="store_true",
        help="Repeat the dry-run validation, then clear the exact selection.",
    )
    parser.add_argument(
        "--approval-id",
        help=(
            "Required with --execute. Record the user approval associated with "
            "the previously presented dry-run."
        ),
    )
    parser.add_argument(
        "--include-succeeded",
        action="store_true",
        help=(
            "Set only_failed=false. Use only for an approved Derived RA "
            "distinctness rerun whose mapped task previously succeeded."
        ),
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Credentials file to load (default: .env).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="configurations.yaml to read; defaults to the nearest one upward.",
    )
    args = parser.parse_args()
    if args.execute and not args.approval_id:
        parser.error("--approval-id is required with --execute")
    if args.plan_only and args.approval_id:
        parser.error("--approval-id is valid only with --execute")

    load_dotenv(args.env_file)
    try:
        entry = load_entry(REGIONS[args.region], find_configuration(args.config))
        host = entry.host()
        username, password = entry.credentials()
    except AirflowConfigError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    task_ids = list(dict.fromkeys(args.task_id))
    requested_task_ids = set(task_ids)
    only_failed = not args.include_succeeded
    path = f"/api/v1/dags/{quote(args.dag_id, safe='')}/clearTaskInstances"

    try:
        plan = post_json(
            host,
            path,
            build_payload(
                args.run_id,
                task_ids,
                dry_run=True,
                only_failed=only_failed,
            ),
            username,
            password,
        )
        planned_references = task_references(plan)
        validate_plan(
            planned_references,
            args.dag_id,
            args.run_id,
            requested_task_ids,
        )
        print_references("Validated rerun plan:", planned_references)
        if args.plan_only:
            return 0

        result = post_json(
            host,
            path,
            build_payload(
                args.run_id,
                task_ids,
                dry_run=False,
                only_failed=only_failed,
            ),
            username,
            password,
        )
        cleared_references = task_references(result)
        validate_plan(
            cleared_references,
            args.dag_id,
            args.run_id,
            requested_task_ids,
        )
        print_references("Airflow accepted for rerun:", cleared_references)
        print(f"Approval: {args.approval_id}")
        print("Task state read-back:")
        for task_id in task_ids:
            task_path = (
                f"/api/v1/dags/{quote(args.dag_id, safe='')}/dagRuns/"
                f"{quote(args.run_id, safe='')}/taskInstances/"
                f"{quote(task_id, safe='')}"
            )
            task = get_json(host, task_path, username, password)
            print(
                f"- {args.dag_id} | {task_id} | {args.run_id} | "
                f"{task.get('state', '<unknown>')}"
            )
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
