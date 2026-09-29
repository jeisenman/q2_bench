import asyncio
from pathlib import Path

import pytest
import yaml

from adapters.warehouse_resolution import ENVIRONMENT_ENV, FIXTURES_ENV
from mcp_servers.warehouse import (
    EnvironmentSecrets,
    describe_warehouse_table,
    run_warehouse_query,
)

SCHEMA = {
    "tables": [
        {
            "schema": "ANALYTICS",
            "name": "JOBS",
            "data": "analytics.jobs.csv",
            "columns": [
                {"name": "ID", "type": "NUMBER"},
                {"name": "CODE", "type": "TEXT"},
            ],
        }
    ]
}


@pytest.fixture(autouse=True)
def sandbox(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "schema.yaml").write_text(yaml.safe_dump(SCHEMA), encoding="utf-8")
    (tmp_path / "analytics.jobs.csv").write_text(
        "ID,CODE\n1,007\n2,042\n", encoding="utf-8"
    )
    monkeypatch.setenv(FIXTURES_ENV, str(tmp_path))
    monkeypatch.setenv(ENVIRONMENT_ENV, "sandbox")


def test_query_route_reports_the_environment_and_determinism() -> None:
    result = asyncio.run(
        run_warehouse_query("SELECT CODE FROM ANALYTICS.JOBS ORDER BY ID")
    )

    assert result["environment"] == "sandbox"
    assert result["deterministic"] is True
    assert result["rows"] == [["007"], ["042"]]
    assert result["row_count"] == len(result["rows"])


def test_query_route_binds_parameters() -> None:
    result = asyncio.run(
        run_warehouse_query(
            "SELECT CODE FROM ANALYTICS.JOBS WHERE ID = $target",
            {"target": 2},
        )
    )

    assert result["rows"] == [["042"]]


def test_query_route_returns_a_structured_portability_error() -> None:
    result = asyncio.run(run_warehouse_query("SELECT CODE:x FROM ANALYTICS.JOBS"))

    assert result["error"] == "not_portable"
    assert any("variant_colon_path" in item for item in result["violations"])


def test_cortex_in_a_query_is_refused_with_the_right_pointer() -> None:
    result = asyncio.run(
        run_warehouse_query(
            "SELECT SNOWFLAKE.CORTEX.SENTIMENT(CODE) FROM ANALYTICS.JOBS"
        )
    )

    assert result["error"] == "not_portable"
    assert any("CortexInference" in item for item in result["violations"])


def test_an_explicit_environment_overrides_the_configured_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENVIRONMENT_ENV, "prod")

    result = asyncio.run(
        run_warehouse_query(
            "SELECT CODE FROM ANALYTICS.JOBS ORDER BY ID",
            None,
            "sandbox",
        )
    )

    assert result["environment"] == "sandbox"


def test_unknown_environment_fails_loudly() -> None:
    with pytest.raises(ValueError, match="unknown environment"):
        asyncio.run(run_warehouse_query("SELECT 1", None, "production"))


def test_describe_route_returns_declared_columns() -> None:
    result = asyncio.run(describe_warehouse_table("ANALYTICS", "JOBS"))

    assert [column["name"] for column in result["columns"]] == ["ID", "CODE"]
    assert result["columns"][0]["type"] == "NUMBER"


def test_secret_lookup_names_the_variable_to_export(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SNOWFLAKE_PROD_PASSWORD", raising=False)

    with pytest.raises(LookupError, match="SNOWFLAKE_PROD_PASSWORD"):
        asyncio.run(EnvironmentSecrets().get_secret("snowflake/prod/password"))


def test_secret_lookup_returns_a_configured_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SNOWFLAKE_DEV_PASSWORD", "value")

    assert (
        asyncio.run(EnvironmentSecrets().get_secret("snowflake/dev/password"))
        == "value"
    )
