import json
import tomllib
from pathlib import Path

import pytest

from adapters.mlflow import (
    CodexTracingConfigurationError,
    CodexTracingConfigurator,
)


def test_configure_writes_user_notify_and_project_destination(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex"
    project_root = tmp_path / "project"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        'model = "gpt-5"\n\n[features]\nweb_search = true\n',
        encoding="utf-8",
    )

    configured = CodexTracingConfigurator(
        codex_home=codex_home,
        project_root=project_root,
    ).configure(
        tracking_uri="http://localhost:5000",
        experiment_id="7",
    )

    codex_config = tomllib.loads(configured.codex_config.read_text())
    tracing_config = json.loads(configured.tracing_config.read_text())
    assert codex_config["notify"] == ["mlflow-codex", "notify-hook"]
    assert codex_config["features"]["web_search"] is True
    assert tracing_config == {
        "trackingUri": "http://localhost:5000",
        "experimentId": "7",
    }


def test_configure_is_idempotent(tmp_path: Path) -> None:
    configurator = CodexTracingConfigurator(
        codex_home=tmp_path / "codex",
        project_root=tmp_path / "project",
    )

    first = configurator.configure(
        tracking_uri="http://localhost:5000",
        experiment_id="0",
    )
    second = configurator.configure(
        tracking_uri="http://mlflow:5000",
        experiment_id="1",
    )

    assert first.codex_config.read_text().count("notify =") == 1
    assert json.loads(second.tracing_config.read_text())["experimentId"] == "1"


def test_configure_rejects_existing_different_notifier(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        'notify = ["existing-hook"]\n',
        encoding="utf-8",
    )

    with pytest.raises(
        CodexTracingConfigurationError,
        match="already defines a notify hook",
    ):
        CodexTracingConfigurator(
            codex_home=codex_home,
            project_root=tmp_path,
        ).configure(
            tracking_uri="http://localhost:5000",
            experiment_id="0",
        )


@pytest.mark.parametrize("field", ["tracking_uri", "experiment_id"])
def test_configure_rejects_empty_required_value(
    tmp_path: Path,
    field: str,
) -> None:
    values = {
        "tracking_uri": "http://localhost:5000",
        "experiment_id": "0",
    }
    values[field] = " "

    with pytest.raises(CodexTracingConfigurationError, match="must not be empty"):
        CodexTracingConfigurator(
            codex_home=tmp_path / "codex",
            project_root=tmp_path,
        ).configure(**values)
