"""One behavioral suite every warehouse backend must satisfy.

The sandbox is only evidence about production if both answer the same way.
These tests run against DuckDB always, and against Snowflake when an
environment is configured. A backend that drifts fails here rather than
silently disagreeing inside a benchmark.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

from adapters.duckdb.fixtures import load_fixture_set
from adapters.duckdb.warehouse import DuckDbWarehouse
from adapters.snowflake.environment import SETTING_SUFFIXES, variable_name
from adapters.snowflake.warehouse import SnowflakeWarehouse
from domain.environments import Environment
from domain.sql_portability import SqlPortabilityError
from ports.warehouse import SqlStatement, Warehouse

CONTRACT_SCHEMA = {
    "tables": [
        {
            "schema": "CONTRACT",
            "name": "ROWS",
            "data": "contract.rows.csv",
            "columns": [
                {"name": "ID", "type": "NUMBER"},
                {"name": "CODE", "type": "TEXT"},
                {"name": "RATIO", "type": "NUMBER(38,4)"},
                {"name": "NOTE", "type": "TEXT"},
            ],
        }
    ]
}
CONTRACT_CSV = """ID,CODE,RATIO,NOTE
1,007,0.2500,present
2,042,1.0000,
"""
SNOWFLAKE_ENVIRONMENT = os.environ.get("WAREHOUSE_CONTRACT_ENVIRONMENT", "").strip()


def _snowflake_configured() -> bool:
    if not SNOWFLAKE_ENVIRONMENT:
        return False
    environment = Environment.parse(SNOWFLAKE_ENVIRONMENT)
    return all(
        os.environ.get(variable_name(environment, suffix), "").strip()
        for suffix in SETTING_SUFFIXES
    )


@pytest.fixture(scope="module")
def sandbox(tmp_path_factory: pytest.TempPathFactory) -> Iterator[DuckDbWarehouse]:
    root: Path = tmp_path_factory.mktemp("contract")
    (root / "schema.yaml").write_text(yaml.safe_dump(CONTRACT_SCHEMA), encoding="utf-8")
    (root / "contract.rows.csv").write_text(CONTRACT_CSV, encoding="utf-8")
    warehouse = DuckDbWarehouse(load_fixture_set(root))
    yield warehouse
    warehouse.close()


@pytest.fixture(
    params=[
        pytest.param("sandbox", id="duckdb"),
        pytest.param(
            "snowflake",
            id="snowflake",
            marks=[
                pytest.mark.production,
                pytest.mark.skipif(
                    not _snowflake_configured(),
                    reason=(
                        "set WAREHOUSE_CONTRACT_ENVIRONMENT and the matching "
                        "SNOWFLAKE_<ENV>_* variables to run this contract "
                        "against a real Snowflake environment"
                    ),
                ),
            ],
        ),
    ]
)
def warehouse(request: pytest.FixtureRequest, sandbox: DuckDbWarehouse) -> Warehouse:
    if request.param == "sandbox":
        return sandbox

    class _EnvironmentSecrets:
        async def get_secret(self, name: str) -> str:
            variable = name.replace("/", "_").replace("-", "_").upper()
            value = os.environ.get(variable, "").strip()
            if not value:
                message = f"secret {name!r} is not set; export {variable}"
                raise LookupError(message)
            return value

    return SnowflakeWarehouse.for_environment(
        Environment.parse(SNOWFLAKE_ENVIRONMENT),
        _EnvironmentSecrets(),
    )


def fetch(warehouse: Warehouse, text: str, **parameters: object):
    return asyncio.run(warehouse.fetch(SqlStatement(text=text, parameters=parameters)))


def test_rows_come_back_in_the_requested_order(warehouse: Warehouse) -> None:
    result = fetch(warehouse, "SELECT CODE FROM CONTRACT.ROWS ORDER BY ID")

    assert result.rows == (("007",), ("042",))


def test_text_columns_preserve_leading_zeros(warehouse: Warehouse) -> None:
    result = fetch(warehouse, "SELECT CODE FROM CONTRACT.ROWS ORDER BY ID LIMIT 1")

    assert result.rows[0][0] == "007"


def test_declared_scale_is_preserved(warehouse: Warehouse) -> None:
    result = fetch(warehouse, "SELECT RATIO FROM CONTRACT.ROWS ORDER BY ID")

    assert result.rows == (("0.2500",), ("1.0000",))


def test_empty_text_is_null_not_an_empty_string(warehouse: Warehouse) -> None:
    result = fetch(
        warehouse,
        "SELECT ID FROM CONTRACT.ROWS WHERE NOTE IS NULL ORDER BY ID",
    )

    # Snowflake returns a native integer; the sandbox renders NUMBER as text.
    assert result.rows in (((2,),), (("2",),))


def test_bound_parameters_filter_rows(warehouse: Warehouse) -> None:
    result = fetch(
        warehouse,
        "SELECT CODE FROM CONTRACT.ROWS WHERE ID = $target ORDER BY ID",
        target=1,
    )

    assert result.rows == (("007",),)


def test_column_metadata_is_reported(warehouse: Warehouse) -> None:
    result = fetch(warehouse, "SELECT ID, CODE FROM CONTRACT.ROWS ORDER BY ID")

    assert [name.upper() for name in result.column_names] == ["ID", "CODE"]


def test_the_environment_is_reported_on_every_result(warehouse: Warehouse) -> None:
    result = fetch(warehouse, "SELECT ID FROM CONTRACT.ROWS ORDER BY ID")

    assert result.environment is warehouse.environment


def test_unportable_sql_is_rejected_by_every_backend(warehouse: Warehouse) -> None:
    with pytest.raises(SqlPortabilityError):
        fetch(warehouse, "SELECT NOTE:region FROM CONTRACT.ROWS")


def test_cortex_is_rejected_by_every_backend(warehouse: Warehouse) -> None:
    with pytest.raises(SqlPortabilityError, match="CortexInference"):
        fetch(warehouse, "SELECT SNOWFLAKE.CORTEX.SENTIMENT(NOTE) FROM CONTRACT.ROWS")
