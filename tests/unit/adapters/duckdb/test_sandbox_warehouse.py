import asyncio
from pathlib import Path

import pytest
import yaml

from adapters.duckdb.fixtures import FixtureError, load_fixture_set
from adapters.duckdb.warehouse import DuckDbWarehouse
from domain.environments import Environment
from domain.sql_portability import SqlPortabilityError
from ports.warehouse import SqlStatement, WarehouseQueryError

SCHEMA = {
    "tables": [
        {
            "schema": "ANALYTICS",
            "name": "FAILED_JOBS",
            "data": "analytics.failed_jobs.csv",
            "columns": [
                {"name": "CLIENT_ID", "type": "VARCHAR"},
                {"name": "CLIENT_CODE", "type": "TEXT"},
                {"name": "FAILED_AT", "type": "TIMESTAMP_TZ"},
                {"name": "ROW_COUNT", "type": "NUMBER"},
                {"name": "RATIO", "type": "NUMBER(38,16)"},
                {"name": "PAYLOAD", "type": "VARIANT"},
                {"name": "NOTE", "type": "TEXT"},
            ],
        }
    ]
}
CSV = """CLIENT_ID,CLIENT_CODE,FAILED_AT,ROW_COUNT,RATIO,PAYLOAD,NOTE
a1b2c3d4-0000-4000-8000-000000000001,007,2026-09-26T05:14:22Z,142,0.3333333333333333,"{""region"":""US""}",
a1b2c3d4-0000-4000-8000-000000000002,042,2026-09-26T06:01:00Z,0,1.0000000000000000,"{""region"":""CA""}",present
"""


@pytest.fixture
def fixture_root(tmp_path: Path) -> Path:
    (tmp_path / "schema.yaml").write_text(yaml.safe_dump(SCHEMA), encoding="utf-8")
    (tmp_path / "analytics.failed_jobs.csv").write_text(CSV, encoding="utf-8")
    return tmp_path


@pytest.fixture
def warehouse(fixture_root: Path) -> DuckDbWarehouse:
    return DuckDbWarehouse(load_fixture_set(fixture_root))


def query(warehouse: DuckDbWarehouse, text: str, **parameters: object):
    return asyncio.run(warehouse.fetch(SqlStatement(text=text, parameters=parameters)))


def test_sandbox_reports_itself_as_deterministic(warehouse: DuckDbWarehouse) -> None:
    assert warehouse.environment is Environment.SANDBOX
    assert warehouse.environment.is_deterministic is True


def test_csv_loads_into_explicitly_typed_columns(warehouse: DuckDbWarehouse) -> None:
    result = query(
        warehouse,
        "SELECT CLIENT_CODE, ROW_COUNT, RATIO FROM ANALYTICS.FAILED_JOBS "
        "ORDER BY CLIENT_CODE",
    )

    # Leading zeros survive, NUMBER is integral, and NUMBER(38,16) keeps scale.
    assert result.rows == (
        ("007", "142", "0.3333333333333333"),
        ("042", "0", "1.0000000000000000"),
    )


def test_empty_csv_field_becomes_null_not_empty_string(
    warehouse: DuckDbWarehouse,
) -> None:
    result = query(
        warehouse,
        "SELECT NOTE IS NULL AS missing FROM ANALYTICS.FAILED_JOBS "
        "ORDER BY CLIENT_CODE",
    )

    assert result.rows == ((True,), (False,))


def test_json_columns_support_path_access(warehouse: DuckDbWarehouse) -> None:
    result = query(
        warehouse,
        "SELECT PAYLOAD->>'region' AS region FROM ANALYTICS.FAILED_JOBS "
        "ORDER BY CLIENT_CODE",
    )

    assert result.rows == (("US",), ("CA",))


def test_parameters_are_bound_not_interpolated(warehouse: DuckDbWarehouse) -> None:
    result = query(
        warehouse,
        "SELECT CLIENT_CODE FROM ANALYTICS.FAILED_JOBS WHERE ROW_COUNT > $floor",
        floor=10,
    )

    assert result.rows == (("007",),)


def test_snowflake_scalar_functions_work_through_compat_macros(
    warehouse: DuckDbWarehouse,
) -> None:
    result = query(
        warehouse,
        "SELECT iff(ROW_COUNT > 0, 'busy', 'idle') AS state, "
        "nvl(NOTE, 'none') AS note, zeroifnull(NULL) AS zero "
        "FROM ANALYTICS.FAILED_JOBS ORDER BY CLIENT_CODE",
    )

    # zeroifnull(NULL) yields an integer literal, so it stays an int.
    assert result.rows == (("busy", "none", 0), ("idle", "present", 0))


def test_unportable_statement_is_rejected_before_execution(
    warehouse: DuckDbWarehouse,
) -> None:
    with pytest.raises(SqlPortabilityError):
        query(warehouse, "SELECT PAYLOAD:region FROM ANALYTICS.FAILED_JOBS")


def test_cortex_is_rejected_from_the_warehouse_path(
    warehouse: DuckDbWarehouse,
) -> None:
    with pytest.raises(SqlPortabilityError, match="CortexInference"):
        query(
            warehouse,
            "SELECT SNOWFLAKE.CORTEX.SENTIMENT(NOTE) FROM ANALYTICS.FAILED_JOBS",
        )


def test_repeated_reads_return_identical_rows(warehouse: DuckDbWarehouse) -> None:
    statement = "SELECT * FROM ANALYTICS.FAILED_JOBS ORDER BY CLIENT_CODE"

    assert query(warehouse, statement).rows == query(warehouse, statement).rows


def test_digest_changes_when_fixture_data_changes(fixture_root: Path) -> None:
    before = load_fixture_set(fixture_root).digest()
    csv_path = fixture_root / "analytics.failed_jobs.csv"
    csv_path.write_text(CSV.replace(",142,", ",143,"), encoding="utf-8")

    assert load_fixture_set(fixture_root).digest() != before


def test_columns_report_declared_warehouse_types(warehouse: DuckDbWarehouse) -> None:
    columns = asyncio.run(warehouse.columns("ANALYTICS", "FAILED_JOBS"))

    assert [column.name for column in columns][:2] == ["CLIENT_ID", "CLIENT_CODE"]
    assert columns[3].type_name == "NUMBER"


def test_unknown_table_fails_with_an_actionable_message(
    warehouse: DuckDbWarehouse,
) -> None:
    with pytest.raises(WarehouseQueryError, match="unknown sandbox table"):
        asyncio.run(warehouse.columns("ANALYTICS", "MISSING"))


def test_csv_header_must_match_declared_columns(fixture_root: Path) -> None:
    csv_path = fixture_root / "analytics.failed_jobs.csv"
    csv_path.write_text(CSV.replace("CLIENT_CODE", "CODE", 1), encoding="utf-8")

    with pytest.raises(FixtureError, match="does not match declared columns"):
        load_fixture_set(fixture_root)


def test_missing_schema_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(FixtureError, match=r"missing schema\.yaml"):
        load_fixture_set(tmp_path)


def test_unsupported_column_type_is_rejected(fixture_root: Path) -> None:
    schema = {"tables": [dict(SCHEMA["tables"][0])]}
    schema["tables"][0]["columns"] = [{"name": "CLIENT_ID", "type": "QUANTUM"}]
    (fixture_root / "schema.yaml").write_text(yaml.safe_dump(schema), encoding="utf-8")
    (fixture_root / "analytics.failed_jobs.csv").write_text(
        "CLIENT_ID\nabc\n", encoding="utf-8"
    )

    with pytest.raises(FixtureError, match="unsupported type"):
        load_fixture_set(fixture_root).tables[0].create_statement()
