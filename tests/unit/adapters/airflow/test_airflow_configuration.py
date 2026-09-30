"""Tests for configurations.yaml-driven Airflow connections."""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.airflow import (
    AirflowApiSource,
    AirflowConfigurationError,
    AirflowEnvironment,
    load_airflow_connection,
)
from workspaces.data_engineering.workflows.prod_support.models import Region

ENTRY = """
      {name}:
        host_env: {prefix}HOST
        user_env: {prefix}USER
        password_env: {prefix}PASSWORD
"""


def _write(tmp_path: Path, *entries: tuple[str, str]) -> Path:
    body = "".join(ENTRY.format(name=name, prefix=prefix) for name, prefix in entries)
    path = tmp_path / "configurations.yaml"
    path.write_text(
        "version: 1\nworkspaces:\n  data_engineering:\n    airflow:\n" + body,
        encoding="utf-8",
    )
    return path


def _environ(prefix: str, host: str = "https://airflow.test/") -> dict[str, str]:
    return {f"{prefix}HOST": host, f"{prefix}USER": "u", f"{prefix}PASSWORD": "p"}


def test_loads_connection_and_strips_trailing_slash(tmp_path: Path) -> None:
    path = _write(tmp_path, ("alpha", "A"))

    connection = load_airflow_connection(AirflowEnvironment.ALPHA, path, _environ("A"))

    assert connection.host == "https://airflow.test"
    assert (connection.username, connection.password) == ("u", "p")


def test_rejects_absent_environment_entry(tmp_path: Path) -> None:
    path = _write(tmp_path, ("alpha", "A"))

    with pytest.raises(AirflowConfigurationError, match=r"airflow\.staging must"):
        load_airflow_connection(AirflowEnvironment.STAGING, path, _environ("A"))


def test_rejects_absent_airflow_section(tmp_path: Path) -> None:
    path = tmp_path / "configurations.yaml"
    path.write_text("version: 1\nworkspaces: {}\n", encoding="utf-8")

    with pytest.raises(AirflowConfigurationError, match="must be a mapping"):
        load_airflow_connection(AirflowEnvironment.PRODUS, path, {})


def test_rejects_absent_key(tmp_path: Path) -> None:
    path = _write(tmp_path, ("alpha", "A"))
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "        password_env: APASSWORD\n", ""
        ),
        encoding="utf-8",
    )

    with pytest.raises(AirflowConfigurationError, match="password_env must be set"):
        load_airflow_connection(AirflowEnvironment.ALPHA, path, _environ("A"))


def test_rejects_empty_variable_values(tmp_path: Path) -> None:
    path = _write(tmp_path, ("alpha", "A"))
    environ = _environ("A") | {"APASSWORD": " "}

    with pytest.raises(AirflowConfigurationError, match="APASSWORD"):
        load_airflow_connection(AirflowEnvironment.ALPHA, path, environ)


def test_rejects_non_https_host(tmp_path: Path) -> None:
    path = _write(tmp_path, ("alpha", "A"))

    with pytest.raises(AirflowConfigurationError, match="https://"):
        load_airflow_connection(
            AirflowEnvironment.ALPHA, path, _environ("A", "http://airflow.test")
        )


def test_source_uses_production_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write(tmp_path, ("produs", "US"), ("prodca", "CA"))
    for key, value in (_environ("US") | _environ("CA")).items():
        monkeypatch.setenv(key, value)

    source = AirflowApiSource.from_configuration(path)

    assert tuple(config.region for config in source._regions) == (
        Region.US_01,
        Region.CA_02,
    )


def test_source_rejects_missing_production_entry(tmp_path: Path) -> None:
    path = _write(tmp_path, ("produs", "US"))

    with pytest.raises(AirflowConfigurationError):
        AirflowApiSource.from_configuration(path)


def test_example_template_names_every_environment() -> None:
    template = Path(__file__).parents[4] / "configurations.yaml.example"
    environ = {
        f"{prefix}{suffix}": "https://airflow.test"
        for prefix in ("ALPHAAIRFLOW", "STAGINGAIRFLOW", "USAIRFLOW", "CAAIRFLOW")
        for suffix in ("HOST", "USER", "PASSWORD")
    } | {"USAIRFLORUSER": "u", "CAAIRFLORUSER": "u"}

    for environment in AirflowEnvironment:
        assert load_airflow_connection(environment, template, environ)
