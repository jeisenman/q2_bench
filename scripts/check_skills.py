"""Run the workspace skill synchronization policy check."""

from __future__ import annotations

import argparse
from pathlib import Path

from repository_checks.skill_sync import (
    SkillSyncError,
    discover_skills,
    plan_sync,
    stale_targets,
)


def main() -> int:
    """Validate that harness skill directories match their workspace sources."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "workspaces_root",
        nargs="?",
        type=Path,
        default=Path("src/workspaces"),
    )
    parser.add_argument("--project-root", type=Path, default=Path())
    args = parser.parse_args()
    try:
        skills = discover_skills(args.workspaces_root)
        plan = plan_sync(args.project_root, skills)
    except SkillSyncError as error:
        parser.exit(1, f"{error}\n")
    problems = stale_targets(args.project_root, plan)
    if problems:
        parser.exit(1, "\n".join(problems) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
