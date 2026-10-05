"""Upload a reviewed DI Pipelines branch with the local dsint helper."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from adapters.local import data_engineering_repositories_root

BRANCH_PATTERN = re.compile(r"^(?:RA-\d{4}|master|main)$", re.IGNORECASE)
MAX_OUTPUT_CHARS = 4_000


class DatabricksIntegrationError(ValueError):
    """Raised when a dsint branch upload is invalid or fails."""

    @classmethod
    def invalid_branch(cls) -> DatabricksIntegrationError:
        """Return the supported branch-name contract."""
        return cls("branch must be master, main, or an RA-#### feature branch")

    @classmethod
    def missing_profile(cls, path: Path) -> DatabricksIntegrationError:
        """Return an error for a missing shell profile."""
        return cls(f"bash profile does not exist: {path}")

    @classmethod
    def missing_checkout(cls, path: Path) -> DatabricksIntegrationError:
        """Return an error for a missing DI Pipelines checkout."""
        return cls(f"DI Pipelines ds-jobs checkout does not exist: {path}")

    @classmethod
    def command_failed(cls, returncode: int, output: str) -> DatabricksIntegrationError:
        """Return bounded output and credential setup guidance."""
        guidance = (
            "Ensure DE_DATABRICKS_HOST and DE_DATABRICKS_TOKEN are exported "
            "in ~/.bash_profile, the Databricks CLI is authenticated, and "
            "dsint is defined."
        )
        return cls(
            f"dsint failed with exit code {returncode}: "
            f"{output[-MAX_OUTPUT_CHARS:]}\n{guidance}"
        )


@dataclass(frozen=True, slots=True)
class DatabricksIntegrationUpload:
    """Non-secret evidence from one completed dsint upload."""

    branch: str
    notebook_path: str
    output: str


def upload_integration_branch(
    branch: str,
    *,
    configuration_path: Path = Path("configurations.yaml"),
    environ: Mapping[str, str] | None = None,
    command_runner: Callable[..., Any] | None = None,
) -> DatabricksIntegrationUpload:
    """Run dsint for master/main or one RA ticket branch."""
    normalized = branch.strip()
    if not BRANCH_PATTERN.fullmatch(normalized):
        raise DatabricksIntegrationError.invalid_branch()
    environment = dict(os.environ if environ is None else environ)
    home = Path(environment.get("HOME", "")).expanduser()
    profile = home / ".bash_profile"
    if not profile.is_file():
        raise DatabricksIntegrationError.missing_profile(profile)
    repository = data_engineering_repositories_root(configuration_path) / "di-pipelines"
    if not (repository / "ds-jobs" / "src").is_dir():
        raise DatabricksIntegrationError.missing_checkout(repository)
    command: Sequence[str] = (
        "bash",
        "-lc",
        'source "$1"; command -v dsint >/dev/null || '
        '{ echo "dsint is not defined in the bash profile"; exit 2; }; dsint "$2"',
        "dsint-mcp",
        str(profile),
        normalized,
    )
    runner = subprocess.run if command_runner is None else command_runner
    result = runner(
        command,
        cwd=repository,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
    if result.returncode:
        raise DatabricksIntegrationError.command_failed(result.returncode, output)
    return DatabricksIntegrationUpload(
        branch=normalized,
        notebook_path=(
            f"/Shared/Data-Science/DI-Pipelines/Integration-Testing/{normalized}"
        ),
        output=output[-MAX_OUTPUT_CHARS:],
    )
