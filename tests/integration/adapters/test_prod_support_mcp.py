import asyncio
import json
from pathlib import Path

import pytest

from adapters.airflow import AirflowApiSource
from adapters.resource_discovery import ResourceDiscoveryApiSource
from mcp_servers.prod_support import (
    EmptyAirflowFailureSource,
    _resource_discovery,
    _source,
    list_prod_support_updates,
    prod_support_definition,
    prod_support_prompt,
    prod_support_updates,
    run_prod_support,
)
from workspaces.data_engineering.agents.prod_support import (
    ReplayAirflowFailureSource,
)
from workspaces.data_engineering.agents.resource_discovery import (
    ResourceDiscoveryAgent,
)

EXPECTED_REGION_COUNT = 2


def test_mcp_tool_runs_prod_support_agent() -> None:
    result = asyncio.run(
        run_prod_support(
            prompt="Investigate the orders pipeline.",
            service="orders",
            correlation_id="incident-1",
        )
    )

    assert result["correlation_id"] == "incident-1"
    assert "PROD SUPPORT" in result["output"]
    assert result["output"].startswith("# Prod Support Report — ")
    assert " operational day\n\nWindow: `" in result["output"]
    assert "URLs to validate\nhttps://airflow-us01" in result["output"]
    assert "Message for developer:" in result["output"]
    assert "Message for Data Internal Channel\n:bangbang:" in result["output"]
    assert "```markdown" not in result["output"]
    assert "Follow Up:\nNo Airflow task retries" in result["output"]
    assert "- Good" in result["output"]
    assert result["developer_report"].startswith("Message for developer:")
    assert result["data_internal_report"].startswith(
        "Message for Data Internal Channel"
    )
    assert len(result["validation_urls"]) == EXPECTED_REGION_COUNT
    assert result["follow_up"] == (
        "No Airflow task retries are suggested for this operational window."
    )
    assert result["attributes"]["service"] == "orders"
    assert result["tool_calls"] == (
        "discover_airflow_failures",
        "fetch_airflow_task_log",
        "inspect_airflow_workload",
        "query_oms_job",
        "classify_failure",
        "trigger_resource_discovery_agent",
    )


def test_mcp_resource_and_prompt_describe_agent() -> None:
    definition = asyncio.run(prod_support_definition())
    prompt = prod_support_prompt("Pipeline failed.")

    assert "production" in definition.lower()
    assert "Request: Pipeline failed." in prompt


def test_mcp_exposes_configured_support_updates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "product_support_updates.json"
    source.write_text(
        json.dumps(
            {
                "updates": [
                    {
                        "client": "Example Bank",
                        "date": "2026-09-26",
                        "environment": "production",
                        "job": "daily-load",
                        "message_ts": "1.0",
                        "permalink": "https://example.test/message",
                        "status": "resolved",
                        "summary": "Recovered.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PROD_SUPPORT_UPDATES_PATH", str(source))

    resource = json.loads(asyncio.run(prod_support_updates()))
    result = asyncio.run(list_prod_support_updates(status="RESOLVED"))

    assert resource["updates"][0]["client"] == "Example Bank"
    assert result["count"] == 1


def test_mcp_source_uses_production_airflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROD_SUPPORT_SOURCE", "production")
    monkeypatch.setenv("USAIRFLORUSER", "us-user")
    monkeypatch.setenv("USAIRFLOWPASSWORD", "us-password")
    monkeypatch.setenv("CAAIRFLORUSER", "ca-user")
    monkeypatch.setenv("CAAIRFLOWPASSWORD", "ca-password")
    monkeypatch.setenv("RESOURCE_DISCOVERY_BASE_URL", "https://resources.test")
    monkeypatch.setenv("RESOURCE_DISCOVERY_TENANT_ID", "tenant")
    monkeypatch.setenv("RESOURCE_DISCOVERY_CLIENT_ID", "client")
    monkeypatch.setenv("RESOURCE_DISCOVERY_CLIENT_SECRET", "secret")
    monkeypatch.setenv("RESOURCE_DISCOVERY_SCOPE", "scope")
    monkeypatch.delenv("PROD_SUPPORT_DATASET", raising=False)

    assert isinstance(_source(), AirflowApiSource)
    resource_discovery = _resource_discovery()
    assert isinstance(resource_discovery, ResourceDiscoveryAgent)
    assert isinstance(resource_discovery._source, ResourceDiscoveryApiSource)


def test_mcp_source_uses_explicit_replay_dataset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "capture.json"
    dataset.write_text(json.dumps({"records": []}), encoding="utf-8")
    monkeypatch.setenv("PROD_SUPPORT_SOURCE", "replay")
    monkeypatch.setenv("PROD_SUPPORT_DATASET", str(dataset))

    assert isinstance(_source(), ReplayAirflowFailureSource)


def test_mcp_source_defaults_to_safe_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PROD_SUPPORT_SOURCE", raising=False)
    monkeypatch.delenv("PROD_SUPPORT_DATASET", raising=False)

    assert isinstance(_source(), EmptyAirflowFailureSource)
    assert _resource_discovery() is None


@pytest.mark.parametrize(
    ("source_mode", "dataset", "message"),
    [
        ("production", "capture.json", "cannot be set"),
        ("replay", None, "is required"),
        ("empty", "capture.json", "cannot be set"),
        ("invalid", None, "unsupported"),
    ],
)
def test_mcp_source_rejects_invalid_configuration(
    monkeypatch: pytest.MonkeyPatch,
    source_mode: str,
    dataset: str | None,
    message: str,
) -> None:
    monkeypatch.setenv("PROD_SUPPORT_SOURCE", source_mode)
    if dataset is None:
        monkeypatch.delenv("PROD_SUPPORT_DATASET", raising=False)
    else:
        monkeypatch.setenv("PROD_SUPPORT_DATASET", dataset)

    with pytest.raises(ValueError, match=message):
        _source()
