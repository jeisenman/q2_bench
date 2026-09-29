"""Tests for user-independent production Azure authentication."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "src/workspaces/data_engineering/skills/prod-support/scripts/azure_auth.py"
)


def load_module():
    """Load the skill script as a test module."""
    spec = importlib.util.spec_from_file_location(
        "prod_support_azure_auth",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
    return module


def test_cli_login_selects_production_by_subscription_id(monkeypatch) -> None:
    module = load_module()
    account = {"id": "other-subscription", "name": "Other"}
    commands: list[list[str]] = []

    def run(command, **kwargs):
        del kwargs
        commands.append(command)
        if command[:3] == ["az", "account", "set"]:
            account["id"] = module.PRODUCTION_SUBSCRIPTION_ID
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(account),
            stderr="",
        )

    monkeypatch.setattr(module.shutil, "which", lambda _: "/usr/bin/az")
    monkeypatch.setattr(module.subprocess, "run", run)
    for name in module.REQUIRED_VARS:
        monkeypatch.delenv(name, raising=False)

    assert module.ensure_azure_login()
    assert commands[1][-1:] == [module.PRODUCTION_SUBSCRIPTION_ID]


def test_cli_login_fails_when_production_subscription_is_unavailable(
    monkeypatch,
) -> None:
    module = load_module()

    def run(command, **kwargs):
        del kwargs
        if command[:3] == ["az", "account", "set"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="forbidden")
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"id": "other-subscription"}),
            stderr="",
        )

    monkeypatch.setattr(module.shutil, "which", lambda _: "/usr/bin/az")
    monkeypatch.setattr(module.subprocess, "run", run)
    for name in module.REQUIRED_VARS:
        monkeypatch.delenv(name, raising=False)

    assert not module.ensure_azure_login()
