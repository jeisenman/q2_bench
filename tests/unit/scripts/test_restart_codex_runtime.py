from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[3] / "scripts" / "restart_codex_runtime.py"
)


def load_module() -> ModuleType:
    """Load the restart utility as a test module."""
    spec = importlib.util.spec_from_file_location(
        "restart_codex_runtime",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_restart_command_refreshes_only_mcp_by_default() -> None:
    restart_codex_runtime = load_module()
    command = restart_codex_runtime.restart_command(include_mlflow=False)

    assert command[-1] == "prod-support-mcp"
    assert "--build" in command
    assert "--force-recreate" in command
    assert "mlflow" not in command


def test_restart_runtime_leaves_codex_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    restart_codex_runtime = load_module()
    calls: list[tuple[list[str], dict[str, Any]]] = []
    monkeypatch.setattr(
        restart_codex_runtime,
        "validate_production_configuration",
        lambda: None,
    )

    def run(command: list[str], **kwargs: Any) -> None:
        calls.append((command, kwargs))

    monkeypatch.setattr(restart_codex_runtime.subprocess, "run", run)

    restart_codex_runtime.restart_runtime(
        include_mlflow=True,
        dry_run=False,
    )

    assert calls == [
        (
            restart_codex_runtime.restart_command(include_mlflow=True),
            {
                "cwd": restart_codex_runtime.PROJECT_ROOT,
                "check": True,
            },
        )
    ]
    assert all("ChatGPT" not in argument for argument in calls[0][0])


def test_restart_runtime_propagates_compose_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    restart_codex_runtime = load_module()
    monkeypatch.setattr(
        restart_codex_runtime,
        "validate_production_configuration",
        lambda: None,
    )

    def run(command: list[str], **kwargs: Any) -> None:
        del kwargs
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(restart_codex_runtime.subprocess, "run", run)

    with pytest.raises(subprocess.CalledProcessError):
        restart_codex_runtime.restart_runtime(
            include_mlflow=False,
            dry_run=False,
        )
