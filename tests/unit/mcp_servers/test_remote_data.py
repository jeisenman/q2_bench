from __future__ import annotations

import asyncio

import pytest

from mcp_servers import remote_data
from mcp_servers.remote_data_notebooks import RemoteDataNotebookError


def test_lists_every_remote_data_target_family() -> None:
    result = asyncio.run(remote_data.list_remote_data_targets())

    assert set(result) == {"adls", "databricks", "oms", "snowflake"}
    assert result["adls"] == {
        "dev": "pladls2usdatamartdev",
        "staging": "pladls2usdatamartpreprod",
        "prod_us": "pladls2usdatamartprod",
        "prod_ca": "pladls2cacdatamartprod",
    }
    assert result["oms"] == {
        "us": "pl-oms-us-primary",
        "ca": "pl-oms-ca-primary",
    }


def test_builds_databricks_boilerplate_for_ra() -> None:
    result = asyncio.run(
        remote_data.make_databricks_notebook("ra", "display(spark.range(1))")
    )

    assert result["target"] == "pl-databricks-us-rapreprod-01"
    assert result["source"].startswith("# Databricks notebook source")
    assert "display(spark.range(1))" in result["source"]


def test_builds_bounded_adls_and_snowflake_notebooks() -> None:
    adls = asyncio.run(
        remote_data.make_adls_notebook(
            "prod_ca",
            "curated",
            "accounts/date=2026-09-29",
            limit=25,
        )
    )
    snowflake = asyncio.run(
        remote_data.make_snowflake_notebook(
            "staging",
            "select * from analytics.accounts",
            limit=10,
        )
    )

    assert adls["target"] == "pladls2cacdatamartprod"
    assert "abfss://curated@pladls2cacdatamartprod" in adls["source"]
    assert "data.limit(25)" in adls["source"]
    assert snowflake["target"] == "staging"
    assert "fetchmany(10)" in snowflake["source"]


def test_rejects_mutating_snowflake_notebook() -> None:
    with pytest.raises(RemoteDataNotebookError, match="read-only"):
        asyncio.run(
            remote_data.make_snowflake_notebook(
                "prod_us",
                "delete from analytics.accounts",
            )
        )


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (
            lambda: remote_data.make_databricks_notebook("unknown", "x = 1"),
            "platform must be one of",
        ),
        (
            lambda: remote_data.make_databricks_notebook("ra", " "),
            "code must not be empty",
        ),
        (
            lambda: remote_data.make_adls_notebook(
                "unknown",
                "curated",
                "accounts",
            ),
            "environment must be one of",
        ),
        (
            lambda: remote_data.make_adls_notebook(
                "dev",
                "curated",
                "accounts",
                file_format="xml",
            ),
            "file_format must be one of",
        ),
        (
            lambda: remote_data.make_adls_notebook(
                "dev",
                "curated",
                "accounts",
                limit=0,
            ),
            "limit must be between",
        ),
        (
            lambda: remote_data.make_snowflake_notebook(
                "unknown",
                "select 1",
            ),
            "environment must be one of",
        ),
    ],
)
def test_rejects_invalid_notebook_requests(call, message) -> None:
    with pytest.raises(RemoteDataNotebookError, match=message):
        asyncio.run(call())


def test_delegates_oms_execution_without_classification(monkeypatch) -> None:
    async def fake_query(environment, region, kql, timespan):
        assert (environment, region, kql, timespan) == (
            "production",
            "us",
            "Table | take 1",
            "PT5M",
        )
        return {"workspace": "pl-oms-us-primary", "columns": [], "rows": []}

    monkeypatch.setattr(remote_data, "execute_oms_query", fake_query)

    result = asyncio.run(
        remote_data.query_oms("production", "us", "Table | take 1", "PT5M")
    )

    assert result["workspace"] == "pl-oms-us-primary"
    assert "classification" not in result
