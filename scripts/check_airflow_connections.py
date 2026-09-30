"""Check authenticated API access to every Airflow deployment.

Reads configurations.yaml and .env, then issues one read-only request per
environment. Exits non-zero when any environment is unconfigured or unreachable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from adapters.airflow import (
    AirflowConfigurationError,
    AirflowConnectivityError,
    AirflowEnvironment,
    check_airflow_connection,
    load_airflow_connection,
)
from adapters.airflow.transport import UrllibAirflowTransport
from adapters.local.configuration import (
    DEFAULT_CONFIGURATION_PATH,
    UserConfigurationError,
)
from cli.prod_support_mcp import configure_environment


def main() -> int:
    """Probe each selected environment and report one line per result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "environments",
        nargs="*",
        help="alpha, staging, produs, or prodca; defaults to all.",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIGURATION_PATH)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args()
    configure_environment(args.env_file)
    names = {environment.value for environment in AirflowEnvironment}
    unknown = sorted(set(args.environments) - names)
    if unknown:
        parser.error(f"unknown environments: {', '.join(unknown)}")
    selected = [AirflowEnvironment(value) for value in args.environments] or list(
        AirflowEnvironment
    )
    transport = UrllibAirflowTransport()
    failures = 0
    for environment in selected:
        try:
            connection = load_airflow_connection(environment, args.config)
            total = check_airflow_connection(connection, transport)
        except (
            AirflowConfigurationError,
            AirflowConnectivityError,
            UserConfigurationError,
            OSError,
        ) as error:
            failures += 1
            sys.stdout.write(f"FAIL {environment}: {type(error).__name__}: {error}\n")
            continue
        sys.stdout.write(f"OK   {environment}: {connection.host} ({total} DAGs)\n")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
