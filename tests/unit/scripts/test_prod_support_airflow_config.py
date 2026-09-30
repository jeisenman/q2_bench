"""Tests for the prod-support skill's configurations.yaml Airflow helper."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = (
    Path(__file__).parents[3]
    / "src/workspaces/data_engineering/skills/prod-support/scripts"
)
TEMPLATE = Path(__file__).parents[3] / "configurations.yaml.example"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "prod_support_airflow_config", SCRIPTS / "airflow_config.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_loads_production_entry_and_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _module()
    monkeypatch.setenv("USAIRFLOWHOST", "https://us.airflow.test/")
    monkeypatch.setenv("USAIRFLORUSER", "u")
    monkeypatch.setenv("USAIRFLOWPASSWORD", "p")

    entry = config.load_entry("produs", TEMPLATE)

    assert entry.host() == "https://us.airflow.test"
    assert entry.credentials() == ("u", "p")


def test_matches_entry_by_hostname(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _module()
    monkeypatch.setenv("ALPHAAIRFLOWHOST", "https://other.test")
    monkeypatch.setenv("STAGINGAIRFLOWHOST", "https://staging.test")

    assert config.entry_for_host("staging.test", TEMPLATE).environment == "staging"
    with pytest.raises(config.AirflowConfigError, match="matches no Airflow host"):
        config.entry_for_host("unknown.test", TEMPLATE)


def test_rejects_missing_values_and_entries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _module()
    monkeypatch.delenv("CAAIRFLOWPASSWORD", raising=False)
    monkeypatch.setenv("CAAIRFLOWHOST", "http://ca.test")
    entry = config.load_entry("prodca", TEMPLATE)
    with pytest.raises(config.AirflowConfigError, match="https://"):
        entry.host()
    with pytest.raises(config.AirflowConfigError, match="CAAIRFLO"):
        entry.credentials()

    path = tmp_path / "configurations.yaml"
    path.write_text("version: 1\nworkspaces: {}\n", encoding="utf-8")
    with pytest.raises(config.AirflowConfigError, match="must be a mapping"):
        config.load_entry("alpha", path)


def test_find_configuration_walks_upward(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _module()
    (tmp_path / "configurations.yaml").write_text("version: 1\n", encoding="utf-8")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    assert config.find_configuration() == tmp_path / "configurations.yaml"
    with pytest.raises(config.AirflowConfigError, match="does not exist"):
        config.find_configuration(tmp_path / "missing.yaml")
