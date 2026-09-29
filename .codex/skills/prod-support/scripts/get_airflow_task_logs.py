#!/usr/bin/env python3
"""Collect an exact Airflow task log through the authenticated UI session."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import quote, urlparse

REGIONS = {
    "airflow-us01.precisionlender.com": ("US-01", "USAIRFLORUSER", "USAIRFLOWPASSWORD"),
    "airflow-ca02.precisionlender.com": ("CA-02", "CAAIRFLORUSER", "CAAIRFLOWPASSWORD"),
}


def load_dotenv(env_file: Path) -> None:
    """Load simple .env entries without replacing exported credentials."""
    if not env_file.is_file():
        return
    for raw_line in env_file.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key.isidentifier() or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def parse_dag_url(value: str) -> tuple[str, str, str, str, str]:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("the DAG URL must be an HTTPS Airflow URL")
    region = REGIONS.get(parsed.hostname)
    if not region:
        raise ValueError(f"unsupported Airflow host: {parsed.hostname}")
    parts = [part for part in parsed.path.split("/") if part]
    try:
        dag_id = parts[parts.index("dags") + 1]
    except (ValueError, IndexError) as error:
        raise ValueError("the URL must contain /dags/<dag-id>/") from error
    region_name, username_env, password_env = region
    return parsed.scheme, parsed.hostname, dag_id, username_env, password_env


def api_path(*parts: str) -> str:
    return "/api/v1/" + "/".join(quote(part, safe="") for part in parts)


def response_json(response, description: str) -> dict[str, object]:
    if not response.ok:
        raise RuntimeError(
            f"{description} failed with HTTP {response.status}: {response.text()[:500]}"
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"{description} returned an unexpected response")
    return payload


def task_instances(
    request,
    dag_id: str,
    run_id: str,
    timeout_ms: int,
) -> list[dict[str, object]]:
    path = api_path("dags", dag_id, "dagRuns", run_id, "taskInstances")
    payload = response_json(
        request.get(path, timeout=timeout_ms),
        f"task-instance query for {run_id}",
    )
    instances = payload.get("task_instances", [])
    return [instance for instance in instances if isinstance(instance, dict)]


def exact_task_instance(
    request,
    dag_id: str,
    run_id: str,
    task_id: str,
    timeout_ms: int,
) -> dict[str, object]:
    path = api_path(
        "dags",
        dag_id,
        "dagRuns",
        run_id,
        "taskInstances",
        task_id,
    )
    return response_json(
        request.get(path, timeout=timeout_ms),
        f"task-instance query for {task_id}",
    )


def select_failed_instances(
    request,
    dag_id: str,
    requested_run: str | None,
    task_id: str | None,
    timeout_ms: int,
) -> tuple[str, list[dict[str, object]]]:
    if requested_run and task_id:
        instance = exact_task_instance(
            request,
            dag_id,
            requested_run,
            task_id,
            timeout_ms,
        )
        if instance.get("state") != "failed":
            raise RuntimeError(
                f"task {task_id!r} is {instance.get('state')!r}, not failed"
            )
        return requested_run, [instance]

    if requested_run:
        candidates = [requested_run]
    else:
        runs = response_json(
            request.get(
                api_path("dags", dag_id, "dagRuns")
                + "?limit=100&order_by=-execution_date",
                timeout=timeout_ms,
            ),
            "DAG-run query",
        ).get("dag_runs", [])
        candidates = [
            run.get("dag_run_id")
            for run in runs
            if isinstance(run, dict) and isinstance(run.get("dag_run_id"), str)
        ]

    for run_id in candidates:
        instances = task_instances(request, dag_id, run_id, timeout_ms)
        failed = [
            instance for instance in instances if instance.get("state") == "failed"
        ]
        if task_id:
            failed = [
                instance for instance in failed if instance.get("task_id") == task_id
            ]
        if failed:
            return run_id, failed
    requested_task = f" for task {task_id!r}" if task_id else ""
    raise RuntimeError(f"no failed task instances found{requested_task}")


def print_log(
    request,
    dag_id: str,
    run_id: str,
    instance: dict[str, object],
    max_chars: int,
    timeout_ms: int,
    try_number_override: int | None,
) -> None:
    task_id = instance.get("task_id")
    if not isinstance(task_id, str):
        raise RuntimeError("Airflow returned a task instance without a task_id")
    try_number = try_number_override or int(instance.get("try_number") or 1)
    path = api_path(
        "dags",
        dag_id,
        "dagRuns",
        run_id,
        "taskInstances",
        task_id,
        "logs",
        str(try_number),
    )
    response = request.get(path, timeout=timeout_ms)
    if not response.ok:
        raise RuntimeError(
            f"log query for {task_id} try {try_number} failed with HTTP {response.status}: {response.text()[:500]}"
        )
    log = response.text()
    if max_chars and len(log) > max_chars:
        log = f"[log truncated to final {max_chars} characters]\n" + log[-max_chars:]
    print(f"Task: {task_id}")
    print(f"State: {instance.get('state')}; try: {try_number}; run: {run_id}")
    print(
        "Timing: start={start}; end={end}; duration={duration}".format(
            start=instance.get("start_date", "<unknown>"),
            end=instance.get("end_date", "<unknown>"),
            duration=instance.get("duration", "<unknown>"),
        )
    )
    print(log)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dag_url", help="Airflow DAG Graph or Grid URL")
    parser.add_argument("--task-id", help="Retrieve only this failed task ID")
    parser.add_argument("--run-id", help="Retrieve failures only from this DAG run")
    parser.add_argument(
        "--max-log-chars",
        type=int,
        default=20_000,
        help="Maximum characters printed per log; use 0 for all (default: 20000)",
    )
    parser.add_argument("--try-number", type=int, help="Explicit attempt number")
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=15_000,
        help="Per-request timeout in milliseconds (default: 15000)",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Credentials file (default: .env)",
    )
    args = parser.parse_args()
    if args.max_log_chars < 0:
        parser.error("--max-log-chars must be zero or greater")
    if args.try_number is not None and args.try_number < 1:
        parser.error("--try-number must be positive")
    if args.timeout_ms < 1:
        parser.error("--timeout-ms must be positive")

    try:
        scheme, host, dag_id, username_env, password_env = parse_dag_url(args.dag_url)
        load_dotenv(args.env_file)
        username = os.environ.get(username_env)
        password = os.environ.get(password_env)
        if not username or not password:
            raise RuntimeError(f"missing {username_env} or {password_env}")
        try:
            from playwright.sync_api import sync_playwright
        except ModuleNotFoundError as error:
            raise RuntimeError(
                "Playwright is not installed. Install the Python playwright package before running this collector."
            ) from error

        with sync_playwright() as playwright:
            request = playwright.request.new_context(
                base_url=f"{scheme}://{host}",
                http_credentials={"username": username, "password": password},
            )
            try:
                run_id, instances = select_failed_instances(
                    request,
                    dag_id,
                    args.run_id,
                    args.task_id,
                    args.timeout_ms,
                )
                for index, instance in enumerate(instances):
                    if index:
                        print("\n" + "=" * 80 + "\n")
                    print_log(
                        request,
                        dag_id,
                        run_id,
                        instance,
                        args.max_log_chars,
                        args.timeout_ms,
                        args.try_number,
                    )
            finally:
                request.dispose()
    except (RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
