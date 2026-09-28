import asyncio
import json
from pathlib import Path

import pytest

from adapters.airflow import AirflowApiSource
from adapters.codex_cli import CodexCliRuntime
from adapters.resource_discovery import (
    IndexedResourceDiscoverySource,
    JsonClientLookupSource,
    ResourceDiscoveryApiSource,
)
from mcp_servers.prod_support import (
    _cluster_health,
    _report_runtime,
    _requests_benchmark_case,
    _resource_discovery,
    _source,
    get_prod_support_omissions,
    list_prod_support_updates,
    prod_support_bench_builder_definition,
    prod_support_definition,
    prod_support_prompt,
    prod_support_updates,
    run_prod_support,
    set_prod_support_omissions,
    setup_prod_support,
)
from mcp_servers.prod_support_output import retry_approval_message
from mcp_servers.prod_support_sources import EmptyAirflowFailureSource, memory
from workspaces.data_engineering.agents.production_support import (
    ReplayAirflowFailureSource,
)
from workspaces.data_engineering.agents.production_support.models import (
    Region,
    RetryCandidate,
)
from workspaces.data_engineering.agents.resource_discovery import (
    ResourceDiscoveryAgent,
)

EXPECTED_REGION_COUNT = 2
EXPECTED_BENCHMARK_CASE_COUNT = 7
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600


def test_retry_approval_message_lists_only_exact_candidates() -> None:
    candidate = RetryCandidate(
        number=1,
        region=Region.CA_02,
        dag_id="l3-main-client",
        run_id="run-1",
        task_id="account_level_opportunity_draw_schedule_history",
        label="Scotiabank (1f0): account_level_opportunity_draw_schedule_history",
    )

    assert retry_approval_message((candidate,)) == (
        "Reply with follow up to execute these re-runs:\n"
        "- Scotiabank (1f0): account_level_opportunity_draw_schedule_history"
    )


def test_mcp_tool_runs_prod_support_agent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PROD_SUPPORT_HOME", str(tmp_path / ".prod_support"))
    result = asyncio.run(
        run_prod_support(
            prompt="Investigate the orders pipeline.",
            service="orders",
            correlation_id="incident-1",
        )
    )

    assert result["correlation_id"] == "incident-1"
    assert result["benchmark_case_count"] == EXPECTED_BENCHMARK_CASE_COUNT
    assert result["warnings"] == ()
    assert "PROD SUPPORT" in result["output"]
    assert result["full_report"] == result["output"]
    assert result["output"].startswith("# Prod Support Report — ")
    assert " operational day\n\nWindow: `" in result["output"]
    assert "URLs to validate\nhttps://airflow-us01" in result["output"]
    assert "Message for developer:" in result["output"]
    assert "\n\n:bangbang: PROD SUPPORT " in result["output"]
    assert "\nUS\n- Good\n\nCA\n- Good\n\nFollow Ups:" in result["output"]
    assert "Message for Data Internal Channel" not in result["output"]
    assert "```markdown" not in result["output"]
    assert "Follow Ups:\n\n- No action is required." in result["output"]
    assert "- Good" in result["output"]
    assert result["developer_report"].startswith("Message for developer:")
    assert result["message_for_developer"] == result["developer_report"]
    assert result["developer_message"] == result["developer_report"]
    assert result["data_internal_report"].startswith(":bangbang: PROD SUPPORT ")
    assert result["message_for_data_internal"] == result["data_internal_report"]
    assert result["data_internal_message"] == result["data_internal_report"]
    assert len(result["validation_urls"]) == EXPECTED_REGION_COUNT
    assert result["links"] == result["validation_urls"]
    assert result["follow_up"] == "- No action is required."
    assert result["follow_up_message"] == "No re-runs are available."
    assert result["attributes"]["service"] == "orders"
    assert result["attributes"]["data_internal_omissions"] == [
        "d2p",
        "mi3",
        "subscriber",
        "maintenance",
        "backfill",
        "cmm",
    ]
    assert result["related_agents"] == {
        "follow_up": "agent://prod-support/follow-up/definition",
        "kpo_sizer": "agent://kpo-sizer/definition",
    }
    assert result["tool_calls"] == (
        "run_prod_support",
        "DelegateToClusterAgent",
        "DelegateToTriageManager",
        "DelegateToFollowUpAgent",
        "DelegateToReporter",
        "DelegateToBenchBuilderAgent",
    )
    assert "benchmark_case" not in result


def test_mcp_tool_accepts_empty_data_internal_omission_override() -> None:
    result = asyncio.run(
        run_prod_support(
            prompt="Investigate the orders pipeline.",
            data_internal_omissions=[],
        )
    )

    assert result["attributes"]["data_internal_omissions"] == []


def test_mcp_builds_benchmark_without_replacing_prod_support_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PROD_SUPPORT_BENCHMARK_ROOT", str(tmp_path))

    result = asyncio.run(
        run_prod_support(
            prompt="Do prod support and build benchmark case.",
            correlation_id="benchmark-1",
        )
    )

    benchmark = result["benchmark_case"]
    assert result["output"] == result["full_report"]
    assert result["message_for_developer"] == result["developer_report"]
    assert result["message_for_data_internal"] == result["data_internal_report"]
    assert result["follow_up"] == "- No action is required."
    assert result["follow_up_message"] == "No re-runs are available."
    assert benchmark["review_required"] is True
    assert Path(benchmark["case"]).is_file()
    assert Path(benchmark["expected_behavior"]).is_file()
    assert result["related_agents"]["bench_builder"] == (
        "agent://prod-support/bench-builder/definition"
    )


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("Do prod support and build benchmark case.", True),
        ("Capture a benchmark while doing prod support.", True),
        ("Do prod support.", False),
        ("Show benchmark results.", False),
        ("Do prod support; do not build a benchmark.", False),
    ],
)
def test_benchmark_request_detection(prompt: str, expected: bool) -> None:
    assert _requests_benchmark_case(prompt) is expected


def test_mcp_sets_up_and_updates_private_omissions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / ".prod_support"
    monkeypatch.setenv("PROD_SUPPORT_HOME", str(root))

    initialized = asyncio.run(setup_prod_support())
    updated = asyncio.run(set_prod_support_omissions(["d2p", "subscriber"]))
    loaded = asyncio.run(get_prod_support_omissions())

    assert initialized["path"] == str(root / "omissions.json")
    assert initialized["data_internal_omissions"] == [
        "d2p",
        "mi3",
        "subscriber",
        "maintenance",
        "backfill",
        "cmm",
    ]
    assert updated["data_internal_omissions"] == ["d2p", "subscriber"]
    assert loaded == updated
    assert root.stat().st_mode & 0o777 == PRIVATE_DIRECTORY_MODE
    assert (root / "omissions.json").stat().st_mode & 0o777 == PRIVATE_FILE_MODE


def test_cluster_health_source_is_production_only(monkeypatch) -> None:
    monkeypatch.delenv("PROD_SUPPORT_SOURCE", raising=False)
    assert _cluster_health() is None

    monkeypatch.setenv("PROD_SUPPORT_SOURCE", "production")
    assert _cluster_health() is not None


@pytest.mark.parametrize(
    ("omissions", "message"),
    [
        (["unknown"], "unsupported Data Internal omission"),
        (["d2p", "d2p"], "duplicate Data Internal omission"),
        ([""], "must contain non-empty strings"),
    ],
)
def test_mcp_tool_rejects_invalid_data_internal_omissions(
    omissions: list[str],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        asyncio.run(
            run_prod_support(
                prompt="Investigate the orders pipeline.",
                data_internal_omissions=omissions,
            )
        )


def test_mcp_resource_and_prompt_describe_agent() -> None:
    definition = asyncio.run(prod_support_definition())
    bench_builder = asyncio.run(prod_support_bench_builder_definition())
    prompt = prod_support_prompt("Pipeline failed.")

    assert "production" in definition.lower()
    assert "benchmark" in bench_builder.lower()
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
    assert isinstance(resource_discovery._source, IndexedResourceDiscoverySource)
    assert isinstance(resource_discovery._source.primary, ResourceDiscoveryApiSource)
    assert isinstance(resource_discovery._source.fallback, JsonClientLookupSource)
    assert isinstance(_report_runtime(), CodexCliRuntime)


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
    assert _report_runtime() is None
    assert memory() is None


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
