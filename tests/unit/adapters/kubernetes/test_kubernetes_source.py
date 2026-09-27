import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from adapters.kubernetes import source
from adapters.kubernetes.source import (
    ClusterHealthScriptError,
    ClusterHealthScriptSource,
)
from workspaces.data_engineering.agents.prod_support import Region

EXPECTED_RESTART_COUNT = 12


def _payload(region: str = "US-01") -> str:
    return json.dumps(
        {
            "region": region,
            "observed_at": "2026-09-27T12:00:00+00:00",
            "pods_healthy": True,
            "restart_count": 12,
            "keda_status": "healthy",
            "symptoms": ["8 active pods are running and ready"],
            "warnings": [],
        }
    )


def test_script_source_parses_cluster_health(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return SimpleNamespace(stdout=_payload())

    monkeypatch.setattr(source.subprocess, "run", fake_run)
    health_source = ClusterHealthScriptSource(tmp_path / "health.py", "python")

    health = asyncio.run(health_source.inspect_health(Region.US_01))

    assert calls == [("python", str(tmp_path / "health.py"), "--region", "US-01")]
    assert health.state.value == "healthy"
    assert health.restart_count == EXPECTED_RESTART_COUNT
    assert health.keda_status == "healthy"


def test_script_source_rejects_invalid_output(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        source.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="not json"),
    )
    health_source = ClusterHealthScriptSource(tmp_path / "health.py")

    with pytest.raises(ClusterHealthScriptError, match="JSON object"):
        asyncio.run(health_source.inspect_health(Region.US_01))


def test_script_source_rejects_wrong_region(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        source.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=_payload("CA-02")),
    )
    health_source = ClusterHealthScriptSource(tmp_path / "health.py")

    with pytest.raises(ClusterHealthScriptError, match="expected 'US-01'"):
        asyncio.run(health_source.inspect_health(Region.US_01))


def test_script_source_resolves_repository_script() -> None:
    health_source = ClusterHealthScriptSource.from_repository()

    assert health_source.script_path.name == "check_prod_cluster_health.py"
    assert health_source.script_path.parent.name == "scripts"
