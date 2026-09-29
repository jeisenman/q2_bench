#!/usr/bin/env python3
"""Discover read-only production Airflow task failures for US-01 and CA-02."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time as time_module
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

HTTP_STATUS_SERVICE_UNAVAILABLE = 503
AIRFLOW_503_MAX_ATTEMPTS = 3
AIRFLOW_503_BACKOFF_SECONDS = 30.0


@dataclass(frozen=True)
class Region:
    name: str
    host: str
    username_env: str
    password_env: str


REGIONS = (
    Region(
        name="US-01",
        host="https://airflow-us01.precisionlender.com",
        username_env="USAIRFLORUSER",
        password_env="USAIRFLOWPASSWORD",
    ),
    Region(
        name="CA-02",
        host="https://airflow-ca02.precisionlender.com",
        username_env="CAAIRFLORUSER",
        password_env="CAAIRFLOWPASSWORD",
    ),
)


def parse_reference_time(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not parsed.tzinfo:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_utc_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not parsed.tzinfo:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def operational_anchor(reference_time: datetime) -> datetime:
    """Return current UTC date minus one day at 05:00:00 UTC."""
    target_date = reference_time.astimezone(UTC).date() - timedelta(days=1)
    return datetime.combine(target_date, time(hour=5), tzinfo=UTC)


def failures_link(region: Region, failed_since: datetime) -> str:
    display_time = failed_since.strftime("%m/%d/%Y %I:%M %p").replace(" 0", " ")
    encoded_end = quote_plus(display_time)
    return f"{region.host}/taskinstance/list/?_flt_3_state=failed&_flt_2_end_date={encoded_end}#"


def load_dotenv(env_file: Path) -> None:
    """Load simple KEY=VALUE entries without overriding exported credentials."""
    if not env_file.is_file():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
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


def failed_task_instances(
    region: Region, failed_since: datetime
) -> list[dict[str, object]]:
    username = os.environ.get(region.username_env)
    password = os.environ.get(region.password_env)
    if not username or not password:
        raise RuntimeError(
            f"missing {region.username_env} or {region.password_env}; set them in the environment or .env"
        )

    authorization = base64.b64encode(f"{username}:{password}".encode()).decode()
    payload = {
        "state": ["failed"],
        "end_date_gte": failed_since.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "page_limit": 1000,
        "page_offset": 0,
    }
    failures: list[dict[str, object]] = []
    endpoint = f"{region.host}/api/v1/dags/~/dagRuns/~/taskInstances/list"

    while True:
        request = Request(
            endpoint,
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Basic {authorization}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        for attempt in range(AIRFLOW_503_MAX_ATTEMPTS):
            try:
                with urlopen(request, timeout=30) as response:
                    result = json.load(response)
                break
            except HTTPError as error:
                if (
                    error.code != HTTP_STATUS_SERVICE_UNAVAILABLE
                    or attempt == AIRFLOW_503_MAX_ATTEMPTS - 1
                ):
                    raise RuntimeError(
                        f"Airflow API returned HTTP {error.code}"
                    ) from error
                time_module.sleep(AIRFLOW_503_BACKOFF_SECONDS)
            except URLError as error:
                raise RuntimeError(
                    f"unable to reach Airflow API: {error.reason}"
                ) from error
        else:
            raise AssertionError("Airflow discovery retry loop did not return")

        page = result.get("task_instances", [])
        failures.extend(page)
        if len(failures) >= result.get("total_entries", 0) or not page:
            return failures
        payload["page_offset"] += len(page)


def print_failures(region: Region, failures: list[dict[str, object]]) -> None:
    print(f"{region.name}: {len(failures)} failed task instance(s)")
    for failure in failures:
        print(
            "  - {dag_id} | {task_id} | {dag_run_id} | started {start_date}".format(
                dag_id=failure.get("dag_id", "<unknown DAG>"),
                task_id=failure.get("task_id", "<unknown task>"),
                dag_run_id=failure.get("dag_run_id", "<unknown run>"),
                start_date=failure.get("start_date", "<not started>"),
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--at",
        help="UTC reference time used to derive the operational anchor; defaults to now.",
    )
    parser.add_argument(
        "--since",
        help=(
            "Explicit UTC failure cutoff. Defaults to current UTC date minus one "
            "day at 05:00:00Z."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the API time window without requesting Airflow.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Credential file to load; defaults to .env.",
    )
    args = parser.parse_args()

    reference_time = parse_reference_time(args.at)
    failed_since = (
        parse_utc_time(args.since) if args.since else operational_anchor(reference_time)
    )
    print(f"Operational anchor: {failed_since.isoformat().replace('+00:00', 'Z')}")
    print("URLs to validate")
    for region in REGIONS:
        print(failures_link(region, failed_since))

    if args.dry_run:
        print(
            f"Would query task instances that failed since {failed_since.isoformat()}"
        )
        return 0

    load_dotenv(args.env_file)
    print("Failed task instances")
    exit_code = 0
    for region in REGIONS:
        try:
            print_failures(region, failed_task_instances(region, failed_since))
        except RuntimeError as error:
            print(f"{region.name}: {error}", file=sys.stderr)
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
