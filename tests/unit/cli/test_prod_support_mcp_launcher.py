from __future__ import annotations

import os
from pathlib import Path

from cli.prod_support_mcp import configure_environment


def test_configure_environment_loads_dotenv_and_defaults_to_production(
    monkeypatch,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "USAIRFLORUSER='us-user'\nCAAIRFLOWPASSWORD=ca-password\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("USAIRFLORUSER", raising=False)
    monkeypatch.delenv("CAAIRFLOWPASSWORD", raising=False)
    monkeypatch.delenv("PROD_SUPPORT_SOURCE", raising=False)

    configure_environment(env_file)

    assert os.environ["USAIRFLORUSER"] == "us-user"
    assert os.environ["CAAIRFLOWPASSWORD"] == "ca-password"
    assert os.environ["PROD_SUPPORT_SOURCE"] == "production"


def test_configure_environment_preserves_explicit_mode_and_credentials(
    monkeypatch,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "USAIRFLORUSER=file-user\nPROD_SUPPORT_SOURCE=production\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("USAIRFLORUSER", "shell-user")
    monkeypatch.setenv("PROD_SUPPORT_SOURCE", "replay")

    configure_environment(env_file)

    assert os.environ["USAIRFLORUSER"] == "shell-user"
    assert os.environ["PROD_SUPPORT_SOURCE"] == "replay"
