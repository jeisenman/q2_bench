"""Cover the Snowflake adapters' own logic without a real connection.

A live Snowflake is exercised by the contract suite when credentials exist.
These tests pin the behavior the adapter owns: parameter binding, value
coercion, error wrapping, lazy connection, and the read-only guard.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from decimal import Decimal

import pytest

from adapters.snowflake import cortex as cortex_module
from adapters.snowflake import warehouse as warehouse_module
from adapters.snowflake.cortex import SnowflakeCortex
from adapters.snowflake.environment import SnowflakeSettings
from adapters.snowflake.warehouse import SnowflakeWarehouse
from domain.environments import Environment
from domain.sql_portability import SqlPortabilityError
from ports.cortex import CortexError, CortexRequest, CortexUnavailableError
from ports.warehouse import SqlStatement, WarehouseQueryError


class FakeCursor:
    """A minimal DB-API cursor that records what it was asked to run."""

    def __init__(self, owner: FakeConnection) -> None:
        self._owner = owner
        self.description: Sequence[Sequence[object]] | None = None
        self._rows: Sequence[Sequence[object]] = ()
        self.closed = False

    def execute(
        self,
        statement: str,
        parameters: Mapping[str, object] | None = None,
    ) -> object:
        self._owner.calls.append((statement, dict(parameters or {})))
        if self._owner.failure is not None:
            raise self._owner.failure
        self.description = self._owner.description
        self._rows = self._owner.rows
        return self

    def fetchall(self) -> Sequence[Sequence[object]]:
        return self._rows

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    """A DB-API connection that serves canned rows."""

    def __init__(
        self,
        description: Sequence[Sequence[object]] = (),
        rows: Sequence[Sequence[object]] = (),
        failure: Exception | None = None,
    ) -> None:
        self.description = description
        self.rows = rows
        self.failure = failure
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.closed = False
        self.opened = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def close(self) -> None:
        self.closed = True


class FakeSecrets:
    """Return a fixed credential and record every lookup."""

    def __init__(self) -> None:
        self.requested: list[str] = []

    async def get_secret(self, name: str) -> str:
        self.requested.append(name)
        return "credential"


def settings(environment: Environment = Environment.PROD) -> SnowflakeSettings:
    return SnowflakeSettings(
        environment=environment,
        account="acct",
        user="user",
        role="role",
        warehouse="wh",
        database="db",
        schema="sch",
        secret_ref="snowflake/prod/password",
    )


@pytest.fixture
def connection(monkeypatch: pytest.MonkeyPatch) -> FakeConnection:
    fake = FakeConnection(
        description=(("CODE", "TEXT"), ("RATIO", "NUMBER")),
        rows=[["007", Decimal("0.2500")]],
    )

    def _open(*_args: object, **_kwargs: object) -> FakeConnection:
        fake.opened += 1
        return fake

    monkeypatch.setattr(warehouse_module, "_open_connection", _open)
    monkeypatch.setattr(cortex_module, "_open_connection", _open)
    return fake


@pytest.mark.usefixtures("connection")
def test_rows_and_columns_come_back_in_port_shape() -> None:
    warehouse = SnowflakeWarehouse(settings(), FakeSecrets())

    result = asyncio.run(
        warehouse.fetch(SqlStatement(text="SELECT CODE, RATIO FROM t ORDER BY CODE"))
    )

    assert result.column_names == ("CODE", "RATIO")
    assert result.environment is Environment.PROD


def test_decimals_render_without_scientific_notation(
    connection: FakeConnection,
) -> None:
    connection.rows = [[Decimal("0E-12")]]
    connection.description = (("RATIO", "NUMBER"),)
    warehouse = SnowflakeWarehouse(settings(), FakeSecrets())

    result = asyncio.run(warehouse.fetch(SqlStatement(text="SELECT RATIO FROM t")))

    assert result.rows == (("0.000000000000",),)


def test_parameters_reach_the_driver_unbound_into_text(
    connection: FakeConnection,
) -> None:
    warehouse = SnowflakeWarehouse(settings(), FakeSecrets())

    asyncio.run(
        warehouse.fetch(
            SqlStatement(
                text="SELECT CODE FROM t WHERE ID = %(target)s",
                parameters={"target": 7},
            )
        )
    )

    statement, parameters = connection.calls[-1]
    assert parameters == {"target": 7}
    assert "7" not in statement


def test_the_connection_opens_once_and_is_reused(connection: FakeConnection) -> None:
    warehouse = SnowflakeWarehouse(settings(), FakeSecrets())

    asyncio.run(warehouse.fetch(SqlStatement(text="SELECT CODE FROM t")))
    asyncio.run(warehouse.fetch(SqlStatement(text="SELECT CODE FROM t")))

    assert connection.opened == 1


@pytest.mark.usefixtures("connection")
def test_the_credential_is_resolved_through_the_secret_provider() -> None:
    secrets = FakeSecrets()
    warehouse = SnowflakeWarehouse(settings(), secrets)

    asyncio.run(warehouse.fetch(SqlStatement(text="SELECT CODE FROM t")))

    assert secrets.requested == ["snowflake/prod/password"]


def test_driver_errors_are_wrapped_with_the_environment(
    connection: FakeConnection,
) -> None:
    connection.failure = RuntimeError("network down")
    warehouse = SnowflakeWarehouse(settings(), FakeSecrets())

    with pytest.raises(WarehouseQueryError, match="Snowflake prod query failed"):
        asyncio.run(warehouse.fetch(SqlStatement(text="SELECT CODE FROM t")))


def test_writes_are_refused_before_reaching_the_driver(
    connection: FakeConnection,
) -> None:
    warehouse = SnowflakeWarehouse(settings(), FakeSecrets())

    with pytest.raises(WarehouseQueryError, match="read-only"):
        asyncio.run(warehouse.fetch(SqlStatement(text="DELETE FROM t")))
    assert connection.calls == []


def test_unportable_sql_is_refused_before_reaching_the_driver(
    connection: FakeConnection,
) -> None:
    warehouse = SnowflakeWarehouse(settings(), FakeSecrets())

    with pytest.raises(SqlPortabilityError):
        asyncio.run(warehouse.fetch(SqlStatement(text="SELECT payload:region FROM t")))
    assert connection.calls == []


def test_schema_introspection_binds_uppercased_names(
    connection: FakeConnection,
) -> None:
    connection.description = (("COLUMN_NAME", "TEXT"), ("DATA_TYPE", "TEXT"))
    connection.rows = [["CODE", "TEXT"]]
    warehouse = SnowflakeWarehouse(settings(), FakeSecrets())

    columns = asyncio.run(warehouse.columns("analytics", "jobs"))

    _, parameters = connection.calls[-1]
    assert parameters == {"schema": "ANALYTICS", "table": "JOBS"}
    assert columns[0].name == "CODE"


def test_tables_are_listed_for_a_schema(connection: FakeConnection) -> None:
    connection.description = (("TABLE_NAME", "TEXT"),)
    connection.rows = [["JOBS"], ["RUNS"]]
    warehouse = SnowflakeWarehouse(settings(), FakeSecrets())

    assert asyncio.run(warehouse.tables("analytics")) == ("JOBS", "RUNS")


def test_closing_releases_the_connection(connection: FakeConnection) -> None:
    warehouse = SnowflakeWarehouse(settings(), FakeSecrets())
    asyncio.run(warehouse.fetch(SqlStatement(text="SELECT CODE FROM t")))

    asyncio.run(warehouse.close())

    assert connection.closed is True


def test_cortex_returns_a_live_completion(connection: FakeConnection) -> None:
    connection.description = (("COMPLETION", "TEXT"),)
    connection.rows = [["ok"]]
    cortex = SnowflakeCortex(settings(Environment.STAGE), FakeSecrets())

    response = asyncio.run(
        cortex.complete(CortexRequest(model="llama3.1-8b", prompt="ping"))
    )

    assert response.text == "ok"
    assert response.environment is Environment.STAGE
    assert response.recorded is False


def test_cortex_binds_the_model_and_prompt(connection: FakeConnection) -> None:
    connection.rows = [["ok"]]
    cortex = SnowflakeCortex(settings(), FakeSecrets())

    asyncio.run(cortex.complete(CortexRequest(model="m", prompt="p")))

    statement, parameters = connection.calls[-1]
    assert "SNOWFLAKE.CORTEX.COMPLETE" in statement
    assert parameters == {"model": "m", "prompt": "p"}


def test_cortex_counts_tokens_without_inference(connection: FakeConnection) -> None:
    connection.rows = [[2]]
    cortex = SnowflakeCortex(settings(), FakeSecrets())
    expected = 2

    assert asyncio.run(cortex.count_tokens("m", "ping")) == expected
    assert "COUNT_TOKENS" in connection.calls[-1][0]


def test_cortex_rejects_a_non_numeric_token_count(connection: FakeConnection) -> None:
    connection.rows = [[object()]]
    cortex = SnowflakeCortex(settings(), FakeSecrets())

    with pytest.raises(CortexError, match="non-numeric token count"):
        asyncio.run(cortex.count_tokens("m", "ping"))


def test_cortex_reports_an_empty_completion(connection: FakeConnection) -> None:
    connection.rows = [[None]]
    cortex = SnowflakeCortex(settings(), FakeSecrets())

    with pytest.raises(CortexError, match="no completion"):
        asyncio.run(cortex.complete(CortexRequest(model="m", prompt="p")))


def test_cortex_errors_are_wrapped_with_the_environment(
    connection: FakeConnection,
) -> None:
    connection.failure = RuntimeError("quota exceeded")
    cortex = SnowflakeCortex(settings(Environment.DEV), FakeSecrets())

    with pytest.raises(CortexError, match="Cortex dev request failed"):
        asyncio.run(cortex.complete(CortexRequest(model="m", prompt="p")))


def test_sandbox_cortex_is_not_served_by_snowflake() -> None:
    with pytest.raises(CortexUnavailableError, match="RecordedCortex"):
        SnowflakeCortex.for_environment(Environment.SANDBOX, FakeSecrets())


def test_closing_cortex_releases_the_connection(connection: FakeConnection) -> None:
    connection.rows = [["ok"]]
    cortex = SnowflakeCortex(settings(), FakeSecrets())
    asyncio.run(cortex.complete(CortexRequest(model="m", prompt="p")))

    asyncio.run(cortex.close())

    assert connection.closed is True
