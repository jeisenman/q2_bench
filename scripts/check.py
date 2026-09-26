"""Run all local repository quality gates."""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Sequence


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

    format_command = ["ruff", "format"]
    if args.check_format:
        format_command.append("--check")
    format_command.append(".")

    run(format_command)
    run(["ruff", "check", "."])
    run(["mypy"])
    run(["pytest"])
    run(["python", "scripts/check_file_lengths.py"])
    run(["python", "scripts/check_agent_docs.py"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
