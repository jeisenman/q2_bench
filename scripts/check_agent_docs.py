"""Run the architecture documentation policy check for agents and workflows."""

from __future__ import annotations

import argparse
from pathlib import Path

from repository_checks.agent_docs import find_errors


def main() -> int:
    """Validate package documentation and return a shell-compatible status."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "roots",
        nargs="*",
        type=Path,
        default=[
            Path("src/workspaces/data_engineering/agents"),
            Path("src/workspaces/data_engineering/workflows"),
        ],
    )
    args = parser.parse_args()
    errors = tuple(error for root in args.roots for error in find_errors(root))
    if errors:
        parser.exit(1, "\n".join(errors) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
