"""Run all local repository quality gates."""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Sequence
from pathlib import Path

GO_EXCLUDED_PARTS = frozenset(
    {".git", ".claude", ".codex", ".venv", "vendor"},
)
PYTHON_PATHS = [
    "scripts/check.py",
    "scripts/check_file_lengths.py",
    "scripts/check_kpo_inventory_sync.py",
    "scripts/restart_codex_runtime.py",
    "src/adapters",
    "src/databricks_runtime",
    "src/workspaces/data_engineering/skills",
    "src/workspaces/data_engineering/benchmarks/prod_bench/dates/09-26-26/assets",
    "tests/unit/adapters/databricks",
    ".claude/skills",
    ".codex/skills",
]


def run(command: Sequence[str]) -> None:
    """Run one quality command and stop on failure."""
    subprocess.run(command, check=True)


def main() -> int:
    """Run formatting, linting, typing, tests, and repository policy checks."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check-format",
        action="store_true",
        help="Check formatting without modifying files.",
    )
    args = parser.parse_args()

    go_files = sorted(
        str(path)
        for path in Path().rglob("*.go")
        if not GO_EXCLUDED_PARTS.intersection(path.parts)
    )
    if go_files:
        go_format_command = ["gofmt"]
        go_format_command.append("-d" if args.check_format else "-w")
        go_format_command.extend(go_files)
        if args.check_format:
            result = subprocess.run(
                go_format_command,
                check=False,
                capture_output=True,
                text=True,
            )
            if result.stdout:
                raise SystemExit(
                    "Go formatting differs; run uv run python scripts/check.py\n"
                    + result.stdout
                )
            if result.returncode:
                raise subprocess.CalledProcessError(
                    result.returncode,
                    go_format_command,
                )
        else:
            run(go_format_command)
        run(["go", "vet", "./..."])
        run(["go", "test", "./..."])

    format_command = ["ruff", "format"]
    if args.check_format:
        format_command.append("--check")
    format_command.extend(PYTHON_PATHS)

    run(format_command)
    run(["ruff", "check", *PYTHON_PATHS])
    run(["python", "scripts/check_kpo_inventory_sync.py"])
    run(["mypy"])
    run(["pytest", "-n", "auto", "--dist", "loadscope"])
    run(["python", "scripts/check_file_lengths.py"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
