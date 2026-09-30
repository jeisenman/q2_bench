"""Tests for the authenticated Airflow connectivity probe."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from adapters.airflow import (
    AirflowConnection,
    AirflowConnectivityError,
    AirflowEnvironment,
    check_airflow_connection,
)
from adapters.airflow.transport import AirflowCredentials

CONNECTION = AirflowConnection(AirflowEnvironment.ALPHA, "https://a.test", "u", "p")


class StubTransport:
    """Return one canned response and record the request."""

    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def request(
        self,
        config: AirflowCredentials,
        method: str,
        path: str,
        payload: Mapping[str, object] | None = None,
    ) -> object:
        del config, payload
        self.calls.append((method, path))
        return self.response


def test_returns_dag_count() -> None:
    transport = StubTransport({"total_entries": 0, "dags": []})

    assert check_airflow_connection(CONNECTION, transport) == 0
    assert transport.calls == [("GET", "/api/v1/dags?limit=1")]


@pytest.mark.parametrize("response", ["<html>login</html>", {"dags": []}])
def test_rejects_unexpected_response(response: object) -> None:
    with pytest.raises(AirflowConnectivityError, match="total_entries"):
        check_airflow_connection(CONNECTION, StubTransport(response))
