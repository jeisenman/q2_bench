"""Authenticated reachability checks for configured Airflow deployments."""

from __future__ import annotations

from adapters.airflow.transport import AirflowCredentials, AirflowTransport

CONNECTIVITY_PATH = "/api/v1/dags?limit=1"


class AirflowConnectivityError(RuntimeError):
    """Raised when Airflow answers an authenticated probe unexpectedly."""


def check_airflow_connection(
    connection: AirflowCredentials,
    transport: AirflowTransport,
) -> int:
    """Return the DAG count after one authenticated API request."""
    response = transport.request(connection, "GET", CONNECTIVITY_PATH)
    total = response.get("total_entries") if isinstance(response, dict) else None
    if not isinstance(total, int):
        message = f"{connection.host}{CONNECTIVITY_PATH} did not return total_entries"
        raise AirflowConnectivityError(message)
    return total
