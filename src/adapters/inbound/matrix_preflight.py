"""Validate recorded evidence inside the candidate runtime before model use."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from adapters.inbound.matrix_runtime import MatrixRunError
from workspaces.data_engineering.benchmarks.matrix_evidence import (
    compact_brief_arguments,
)

if TYPE_CHECKING:
    from workspaces.data_engineering.benchmarks.matrix import MatrixManifest

PREFLIGHT_TIMEOUT_SECONDS = 120


def preflight_recorded_evidence(
    manifest: MatrixManifest,
    workspace: Path,
) -> None:
    """Run the case's deterministic parser before invoking candidate models."""
    arguments = compact_brief_arguments(manifest, "/tmp/preflight-evidence.json")
    if arguments is None:
        return
    command = (
        _container_command(manifest, workspace, arguments)
        if manifest.runtime == "container"
        else [sys.executable, *arguments]
    )
    environment = None
    if manifest.runtime != "container":
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(workspace / "src"),
        }
    process = subprocess.run(
        command,
        cwd=workspace,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=PREFLIGHT_TIMEOUT_SECONDS,
    )
    if process.returncode != 0:
        detail = process.stderr.strip().splitlines()
        reason = detail[-1] if detail else f"exit code {process.returncode}"
        raise MatrixRunError.preflight_failed(reason)


def _container_command(
    manifest: MatrixManifest,
    workspace: Path,
    arguments: tuple[str, ...],
) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--read-only",
        "--user",
        "1000:1000",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "128",
        "--memory",
        "1g",
        "--cpus",
        "1",
        "--env",
        "PYTHONPATH=/evaluation/src",
        "--tmpfs",
        "/tmp:uid=1000,gid=1000,mode=0700",
        "--volume",
        f"{workspace.resolve()}:/evaluation:ro",
        "--workdir",
        "/evaluation",
        "--entrypoint",
        "python3",
        manifest.container_image,
        *arguments,
    ]
