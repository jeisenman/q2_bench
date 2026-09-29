from __future__ import annotations

import json

import pytest

from adapters.airflow import AirflowApiSource
from adapters.mcp import (
    AirflowMcpSource,
    OmsMcpSource,
    ResourceDiscoveryMcpSource,
)
from adapters.oms import AzureOmsJobEvidenceSource
from mcp_servers.prod_support_sources import (
    EmptyAirflowFailureSource,
    airflow_source,
    oms_evidence,
    resource_discovery,
)
from workspaces.data_engineering.agents.production_support import (
    ReplayAirflowFailureSource,
)


def _airflow_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USAIRFLORUSER", "us-user")
    monkeypatch.setenv("USAIRFLOWPASSWORD", "us-password")
    monkeypatch.setenv("CAAIRFLORUSER", "ca-user")
    monkeypatch.setenv("CAAIRFLOWPASSWORD", "ca-password")


@pytest.mark.parametrize("mode", ["direct", "production"])
def test_direct_mode_uses_live_adapters(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    _airflow_environment(monkeypatch)
    monkeypatch.setenv("PROD_SUPPORT_SOURCE", mode)
    monkeypatch.delenv("PROD_SUPPORT_DATASET", raising=False)

    assert isinstance(airflow_source(), AirflowApiSource)
    assert isinstance(oms_evidence(), AzureOmsJobEvidenceSource)


def test_mcp_mode_uses_capability_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROD_SUPPORT_SOURCE", "mcp")
    monkeypatch.delenv("PROD_SUPPORT_DATASET", raising=False)

    airflow = airflow_source()
    resources = resource_discovery()

    assert isinstance(airflow, AirflowMcpSource)
    assert isinstance(oms_evidence(), OmsMcpSource)
    assert resources is not None
    assert isinstance(resources._source, ResourceDiscoveryMcpSource)


def test_replay_and_empty_modes_remain_network_free(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    dataset = tmp_path / "capture.json"
    dataset.write_text(json.dumps({"records": []}), encoding="utf-8")
    monkeypatch.setenv("PROD_SUPPORT_SOURCE", "replay")
    monkeypatch.setenv("PROD_SUPPORT_DATASET", str(dataset))

    assert isinstance(airflow_source(), ReplayAirflowFailureSource)
    assert oms_evidence() is None
    assert resource_discovery() is None

    monkeypatch.setenv("PROD_SUPPORT_SOURCE", "empty")
    monkeypatch.delenv("PROD_SUPPORT_DATASET")
    assert isinstance(airflow_source(), EmptyAirflowFailureSource)


def test_mcp_mode_rejects_replay_dataset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROD_SUPPORT_SOURCE", "mcp")
    monkeypatch.setenv("PROD_SUPPORT_DATASET", "capture.json")

    with pytest.raises(ValueError, match="cannot be set"):
        airflow_source()
