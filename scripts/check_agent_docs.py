"""Run the agent architecture documentation policy check."""

from __future__ import annotations

import argparse
from pathlib import Path

from repository_checks.agent_docs import find_errors


def main() -> int:
    """Validate agent documentation and return a shell-compatible status."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "agents_root",
        nargs="?",
        type=Path,
        default=Path("src/workspaces/data_engineering/agents"),
    )
    args = parser.parse_args()
    errors = find_errors(args.agents_root)
    if errors:
        parser.exit(1, "\n".join(errors) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
