"""Restart the local Codex app and project MCP runtime."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / ".codex" / "config.toml"
APP_SERVER_MARKER = ".bedrock_codex/packages/app-server-daemon/"
MLFLOW_COMMAND_MARKER = "mlflow server --host 127.0.0.1 --port 5000"


class ProductionConfigurationError(RuntimeError):
    """Raised when the local MCP is not configured for production mode."""

    def __init__(self, source: object) -> None:
        """Describe the invalid configured source."""
        super().__init__(
            f"{CONFIG_PATH} must set PROD_SUPPORT_SOURCE=production; got {source!r}"
        )


def process_table() -> list[tuple[int, str]]:
    """Return local process IDs and command lines."""
    result = subprocess.run(
        ["ps", "-axo", "pid=,command="],
        check=True,
        capture_output=True,
        text=True,
    )
    processes: list[tuple[int, str]] = []
    for line in result.stdout.splitlines():
        value = line.strip()
        if not value:
            continue
        pid_text, _, command = value.partition(" ")
        if pid_text.isdigit() and command:
            processes.append((int(pid_text), command.strip()))
    return processes


def matching_pids(marker: str) -> list[int]:
    """Return exact local process IDs whose command contains a marker."""
    current_pid = os.getpid()
    return [
        pid
        for pid, command in process_table()
        if pid != current_pid and marker in command
    ]


def mcp_pids() -> list[int]:
    """Return project-local MCP server process IDs."""
    current_pid = os.getpid()
    return [
        pid
        for pid, command in process_table()
        if pid != current_pid
        and str(PROJECT_ROOT) in command
        and "prod-support-mcp" in command
    ]


def validate_production_configuration() -> None:
    """Require the project MCP configuration to select live production mode."""
    with CONFIG_PATH.open("rb") as config_file:
        configuration = tomllib.load(config_file)
    source = (
        configuration.get("mcp_servers", {})
        .get("prod_support", {})
        .get("env", {})
        .get("PROD_SUPPORT_SOURCE")
    )
    if source != "production":
        raise ProductionConfigurationError(source)


def terminate_processes(pids: list[int], *, dry_run: bool) -> None:
    """Terminate only the explicitly matched process IDs."""
    for pid in pids:
        if dry_run:
            sys.stdout.write(f"would terminate PID {pid}\n")
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
    if dry_run or not pids:
        return
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        remaining = [pid for pid in pids if _is_running(pid)]
        if not remaining:
            return
        time.sleep(0.2)
    for pid in pids:
        if _is_running(pid):
            os.kill(pid, signal.SIGKILL)


def _is_running(pid: int) -> bool:
    """Return whether a process still exists."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def quit_chatgpt(*, dry_run: bool) -> None:
    """Quit the ChatGPT desktop app so its managed app-server restarts."""
    if dry_run:
        sys.stdout.write("would quit ChatGPT\n")
        return
    subprocess.run(
        ["osascript", "-e", 'tell application "ChatGPT" to quit'],
        check=False,
    )


def launch_chatgpt(*, dry_run: bool) -> None:
    """Launch the ChatGPT desktop app."""
    if dry_run:
        sys.stdout.write("would launch ChatGPT\n")
        return
    subprocess.run(["open", "-a", "ChatGPT"], check=True)


def restart_runtime(*, include_mlflow: bool, dry_run: bool) -> None:
    """Restart the local MCP runtime and optionally MLflow."""
    validate_production_configuration()
    if include_mlflow:
        terminate_processes(
            matching_pids(MLFLOW_COMMAND_MARKER),
            dry_run=dry_run,
        )
    terminate_processes(mcp_pids(), dry_run=dry_run)
    quit_chatgpt(dry_run=dry_run)
    terminate_processes(matching_pids(APP_SERVER_MARKER), dry_run=dry_run)
    launch_chatgpt(dry_run=dry_run)
    if include_mlflow and not dry_run:
        subprocess.Popen(
            [
                "uv",
                "run",
                "mlflow",
                "server",
                "--host",
                "127.0.0.1",
                "--port",
                "5000",
                "--backend-store-uri",
                "sqlite:///var/mlflow/backend.db",
                "--default-artifact-root",
                "./var/mlflow/artifacts",
            ],
            cwd=PROJECT_ROOT,
            start_new_session=True,
        )


def main() -> int:
    """Parse options and restart the configured local runtime."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--with-mlflow",
        action="store_true",
        help="Also restart the local MLflow server.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the exact restart actions without changing processes.",
    )
    args = parser.parse_args()
    restart_runtime(include_mlflow=args.with_mlflow, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
