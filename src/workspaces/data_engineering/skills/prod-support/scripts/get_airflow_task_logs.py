#!/usr/bin/env python3
"""Collect exact Airflow task logs through the authenticated REST API."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

REGIONS = {
    "airflow-us01.precisionlender.com": ("USAIRFLORUSER", "USAIRFLOWPASSWORD"),
    "airflow-ca02.precisionlender.com": ("CAAIRFLORUSER", "CAAIRFLOWPASSWORD"),
}
TRANSIENT_STATUS_CODES = frozenset({502, 503})
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 30.0


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
    """Return the Airflow host, DAG ID, and credential variable names."""
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("the DAG URL must be an HTTPS Airflow URL")
    credentials = REGIONS.get(parsed.hostname)
    if credentials is None:
        raise ValueError(f"unsupported Airflow host: {parsed.hostname}")
    parts = [part for part in parsed.path.split("/") if part]
    try:
        dag_id = parts[parts.index("dags") + 1]
    except (ValueError, IndexError) as error:
        raise ValueError("the URL must contain /dags/<dag-id>/") from error
    username_env, password_env = credentials
    return parsed.scheme, parsed.hostname, dag_id, username_env, password_env


def api_path(*parts: str) -> str:
    """Build an encoded Airflow API path."""
    return "/api/v1/" + "/".join(quote(part, safe="") for part in parts)


@dataclass(frozen=True, slots=True)
class AirflowApiClient:
    """Authenticated, retrying Airflow REST client."""

    base_url: str
    username: str
    password: str
    timeout_ms: int

    def request(self, path: str) -> str:
        """Return one Airflow response body as text."""
        token = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        request = Request(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Basic {token}"},
            method="GET",
        )
        for attempt in range(MAX_ATTEMPTS):
            try:
                with urlopen(request, timeout=self.timeout_ms / 1000) as response:
                    return response.read().decode()
            except HTTPError as error:
                body = error.read().decode(errors="replace")[:500]
                if error.code in TRANSIENT_STATUS_CODES and attempt < MAX_ATTEMPTS - 1:
                    time.sleep(BACKOFF_SECONDS)
                    continue
                raise RuntimeError(
                    f"Airflow request {path} failed with HTTP {error.code}: {body}"
                ) from error
            except URLError as error:
                raise RuntimeError(f"Airflow request {path} failed: {error}") from error
        raise AssertionError

    def json(self, path: str) -> object:
        """Return one decoded Airflow JSON response."""
        try:
            return json.loads(self.request(path))
        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"Airflow request {path} returned invalid JSON"
            ) from error


def response_object(response: object, description: str) -> dict[str, object]:
    """Validate an Airflow object response."""
    if not isinstance(response, dict):
        raise RuntimeError(f"{description} returned an unexpected response")
    return response


def task_instances(
    client: AirflowApiClient,
    dag_id: str,
    run_id: str,
) -> list[dict[str, object]]:
    """Return task instances for one DAG run."""
    payload = response_object(
        client.json(api_path("dags", dag_id, "dagRuns", run_id, "taskInstances")),
        f"task-instance query for {run_id}",
    )
    instances = payload.get("task_instances", [])
    return [instance for instance in instances if isinstance(instance, dict)]


def exact_task_instance(
    client: AirflowApiClient,
    dag_id: str,
    run_id: str,
    task_id: str,
) -> dict[str, object]:
    """Return one exact task instance."""
    return response_object(
        client.json(
            api_path("dags", dag_id, "dagRuns", run_id, "taskInstances", task_id)
        ),
        f"task-instance query for {task_id}",
    )


def select_failed_instances(
    client: AirflowApiClient,
    dag_id: str,
    requested_run: str | None,
    task_id: str | None,
) -> tuple[str, list[dict[str, object]]]:
    """Select exact failed task instances from Airflow."""
    if requested_run and task_id:
        instance = exact_task_instance(client, dag_id, requested_run, task_id)
        if instance.get("state") != "failed":
            raise RuntimeError(
                f"task {task_id!r} is {instance.get('state')!r}, not failed"
            )
        return requested_run, [instance]

    if requested_run:
        candidates = [requested_run]
    else:
        payload = response_object(
            client.json(
                api_path("dags", dag_id, "dagRuns")
                + "?limit=100&order_by=-execution_date"
            ),
            "DAG-run query",
        )
        runs = payload.get("dag_runs", [])
        candidates = [
            run.get("dag_run_id")
            for run in runs
            if isinstance(run, dict) and isinstance(run.get("dag_run_id"), str)
        ]

    for run_id in candidates:
        instances = task_instances(client, dag_id, run_id)
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


def fetch_log(
    client: AirflowApiClient,
    dag_id: str,
    run_id: str,
    instance: dict[str, object],
    try_number_override: int | None,
) -> tuple[dict[str, object], int, str]:
    """Fetch one exact task log."""
    task_id = instance.get("task_id")
    if not isinstance(task_id, str):
        raise RuntimeError("Airflow returned a task instance without a task_id")
    try_number = try_number_override or int(instance.get("try_number") or 1)
    body = client.request(
        api_path(
            "dags",
            dag_id,
            "dagRuns",
            run_id,
            "taskInstances",
            task_id,
            "logs",
            str(try_number),
        )
    )
    return instance, try_number, body


def print_logs_batch(
    client: AirflowApiClient,
    dag_id: str,
    run_id: str,
    instances: list[dict[str, object]],
    max_chars: int,
    try_number_override: int | None,
) -> None:
    """Fetch selected task logs concurrently through the Airflow API."""
    worker_count = min(8, max(1, len(instances)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        results = list(
            executor.map(
                lambda instance: fetch_log(
                    client,
                    dag_id,
                    run_id,
                    instance,
                    try_number_override,
                ),
                instances,
            )
        )
    for index, (instance, try_number, log) in enumerate(results):
        if index:
            print("\n" + "=" * 80 + "\n")
        if max_chars and len(log) > max_chars:
            log = (
                f"[log truncated to final {max_chars} characters]\n" + log[-max_chars:]
            )
        print(f"Task: {instance.get('task_id')}")
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
    """Run the exact Airflow API log collector."""
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
        client = AirflowApiClient(
            f"{scheme}://{host}",
            username,
            password,
            args.timeout_ms,
        )
        run_id, instances = select_failed_instances(
            client,
            dag_id,
            args.run_id,
            args.task_id,
        )
        print_logs_batch(
            client,
            dag_id,
            run_id,
            instances,
            args.max_log_chars,
            args.try_number,
        )
    except (RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
