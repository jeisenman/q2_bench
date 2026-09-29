from pathlib import Path

import pytest
import yaml

from adapters.duckdb.warehouse import DuckDbWarehouse
from adapters.warehouse_resolution import (
    CORTEX_RECORDINGS_ENV,
    ENVIRONMENT_ENV,
    FIXTURES_ENV,
    EnvironmentResolutionError,
    configured_environment,
    resolve_cortex,
    resolve_warehouse,
)
from domain.environments import Environment

SCHEMA = {
    "tables": [
        {
            "schema": "S",
            "name": "T",
            "data": "s.t.csv",
            "columns": [{"name": "ID", "type": "NUMBER"}],
        }
    ]
}


@pytest.fixture
def fixtures(tmp_path: Path) -> Path:
    (tmp_path / "schema.yaml").write_text(yaml.safe_dump(SCHEMA), encoding="utf-8")
    (tmp_path / "s.t.csv").write_text("ID\n1\n", encoding="utf-8")
    return tmp_path


def test_sandbox_resolves_to_duckdb_without_any_secret(
    monkeypatch: pytest.MonkeyPatch,
    fixtures: Path,
) -> None:
    monkeypatch.setenv(FIXTURES_ENV, str(fixtures))

    warehouse = resolve_warehouse(Environment.SANDBOX)

    assert isinstance(warehouse, DuckDbWarehouse)
    assert warehouse.environment is Environment.SANDBOX


def test_sandbox_without_fixtures_fails_with_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(FIXTURES_ENV, raising=False)

    with pytest.raises(EnvironmentResolutionError, match=FIXTURES_ENV):
        resolve_warehouse(Environment.SANDBOX)


@pytest.mark.parametrize(
    "environment", [Environment.DEV, Environment.STAGE, Environment.PROD]
)
def test_real_environments_require_a_secret_provider(
    environment: Environment,
) -> None:
    with pytest.raises(EnvironmentResolutionError, match="SecretProvider"):
        resolve_warehouse(environment)


def test_sandbox_cortex_requires_recordings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CORTEX_RECORDINGS_ENV, raising=False)

    with pytest.raises(EnvironmentResolutionError, match=CORTEX_RECORDINGS_ENV):
        resolve_cortex(Environment.SANDBOX)


def test_real_cortex_requires_a_secret_provider() -> None:
    with pytest.raises(EnvironmentResolutionError, match="SecretProvider"):
        resolve_cortex(Environment.PROD)


def test_the_default_environment_is_the_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENVIRONMENT_ENV, raising=False)

    assert configured_environment() is Environment.SANDBOX


def test_the_environment_is_read_from_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENVIRONMENT_ENV, "stage")

    assert configured_environment() is Environment.STAGE
