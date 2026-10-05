"""Tests for the dsint Databricks integration adapter."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from adapters.databricks.integration import (
    DatabricksIntegrationError,
    upload_integration_branch,
)


def configured_checkout(tmp_path: Path) -> tuple[Path, Path]:
    """Create the minimum configured DI Pipelines checkout."""
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bash_profile").write_text("function dsint() { :; }\n", encoding="utf-8")
    repositories = tmp_path / "repositories"
    (repositories / "di-pipelines" / "ds-jobs" / "src").mkdir(parents=True)
    configuration = tmp_path / "configurations.yaml"
    configuration.write_text(
        "\n".join(
            (
                "version: 1",
                "workspaces:",
                "  data_engineering:",
                "    repositories:",
                f"      root: {repositories}",
            )
        ),
        encoding="utf-8",
    )
    return home, configuration


def test_uploads_selected_branch_without_returning_credentials(tmp_path: Path) -> None:
    home, configuration = configured_checkout(tmp_path)
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="Using branch: RA-1234", stderr="")

    result = upload_integration_branch(
        "RA-1234",
        configuration_path=configuration,
        environ={"HOME": str(home), "DE_DATABRICKS_TOKEN": "secret"},
        command_runner=run,
    )

    assert result.branch == "RA-1234"
    assert result.notebook_path.endswith("/RA-1234")
    assert "secret" not in result.output
    assert calls[0][0][-1] == "RA-1234"


def test_rejects_unbounded_branch_name() -> None:
    with pytest.raises(DatabricksIntegrationError, match="RA-####"):
        upload_integration_branch("feature/arbitrary")


def test_failed_upload_returns_setup_guidance(tmp_path: Path) -> None:
    home, configuration = configured_checkout(tmp_path)

    def run(_command, **_kwargs):
        return SimpleNamespace(returncode=2, stdout="", stderr="dsint missing")

    with pytest.raises(DatabricksIntegrationError, match="DE_DATABRICKS_TOKEN"):
        upload_integration_branch(
            "master",
            configuration_path=configuration,
            environ={"HOME": str(home)},
            command_runner=run,
        )
