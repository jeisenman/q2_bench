from __future__ import annotations

import asyncio
import hashlib

import pytest

from adapters.databricks import DatabricksIntegrationUpload, SubmittedDatabricksRun
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
    assert (
        result["source_sha256"] == hashlib.sha256(result["source"].encode()).hexdigest()
    )


def test_delegates_reviewed_databricks_run_submission(monkeypatch) -> None:
    timeout_seconds = 600

    def fake_submit(request):
        assert request.platform == "ra"
        assert request.source == "# Databricks notebook source\n"
        assert request.source_sha256 == "digest"
        assert request.existing_cluster_id == "cluster-123"
        assert request.run_name == "investigation"
        assert request.timeout_seconds == timeout_seconds
        return SubmittedDatabricksRun(
            target="pl-databricks-us-rapreprod-01",
            notebook_path="/Shared/remote-data-mcp/ra/digest",
            run_id=42,
            source_sha256="digest",
        )

    monkeypatch.setattr(remote_data, "submit_databricks_run", fake_submit)

    result = asyncio.run(
        remote_data.run_databricks_notebook(
            "ra",
            "# Databricks notebook source\n",
            "digest",
            "cluster-123",
            options={
                "run_name": "investigation",
                "timeout_seconds": timeout_seconds,
            },
        )
    )

    assert result == {
        "target": "pl-databricks-us-rapreprod-01",
        "notebook_path": "/Shared/remote-data-mcp/ra/digest",
        "run_id": 42,
        "source_sha256": "digest",
        "status": "submitted",
    }


def test_delegates_dsint_branch_upload(monkeypatch) -> None:
    def fake_upload(branch):
        assert branch == "RA-1234"
        return DatabricksIntegrationUpload(
            branch=branch,
            notebook_path="/Shared/Data-Science/DI-Pipelines/Integration-Testing/RA-1234",
            output="Using branch: RA-1234",
        )

    monkeypatch.setattr(remote_data, "upload_integration_branch", fake_upload)

    result = asyncio.run(remote_data.upload_databricks_integration_branch("RA-1234"))

    assert result["status"] == "uploaded"
    assert result["credential_requirements"] == [
        "DE_DATABRICKS_HOST",
        "DE_DATABRICKS_TOKEN",
    ]
    assert "token" not in result


def test_rejects_unknown_databricks_run_option() -> None:
    with pytest.raises(ValueError, match="unsupported options: wait"):
        asyncio.run(
            remote_data.run_databricks_notebook(
                "ra",
                "# Databricks notebook source\n",
                "digest",
                "cluster-123",
                options={"wait": True},
            )
        )


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
            "select * from analytics.accounts",
            environment="staging",
            limit=10,
        )
    )

    assert adls["target"] == "pladls2cacdatamartprod"
    assert "abfss://curated@pladls2cacdatamartprod" in adls["source"]
    assert "data.limit(25)" in adls["source"]
    assert snowflake["target"] == "staging"
    assert "fetchmany(10)" in snowflake["source"]


def test_snowflake_defaults_to_us_production() -> None:
    result = asyncio.run(remote_data.make_snowflake_notebook("select 1"))

    assert result["target"] == "prod_us"
    assert 'os.environ["SNOWFLAKE_PROD_US_ACCOUNT"]' in result["source"]


def test_rejects_mutating_snowflake_notebook() -> None:
    with pytest.raises(RemoteDataNotebookError, match="read-only"):
        asyncio.run(
            remote_data.make_snowflake_notebook(
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
                "select 1",
                environment="unknown",
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
