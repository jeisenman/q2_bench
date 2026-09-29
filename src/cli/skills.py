"""Commands for syncing workspace-owned skills into harness directories."""

from __future__ import annotations

from pathlib import Path

import click

from repository_checks.skill_sync import (
    HARNESS_ROOTS,
    apply_plan,
    discover_skills,
    plan_sync,
    stale_targets,
)

DEFAULT_WORKSPACES_ROOT = Path("src/workspaces")


@click.command("sync-skills")
@click.option(
    "--workspaces-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=DEFAULT_WORKSPACES_ROOT,
    show_default=True,
    help="Directory containing workspace packages.",
)
@click.option(
    "--project-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path(),
    show_default=True,
    help="Repository root that owns the harness skill directories.",
)
@click.option(
    "--check",
    is_flag=True,
    help="Report drift and exit non-zero instead of writing files.",
)
def sync_skills(workspaces_root: Path, project_root: Path, check: bool) -> None:
    """Generate harness skill directories from workspace skill sources."""
    skills = discover_skills(workspaces_root)
    if not skills:
        message = f"no skills found beneath {workspaces_root}/*/skills"
        raise click.ClickException(message)
    plan = plan_sync(project_root, skills)
    if check:
        problems = stale_targets(project_root, plan)
        if problems:
            raise click.ClickException("\n".join(problems))
        click.echo(f"{len(plan.files)} generated skill files are current")
        return
    written = apply_plan(project_root, plan)
    for skill in skills:
        targets = ", ".join(HARNESS_ROOTS[harness] for harness in skill.harnesses)
        click.echo(f"{skill.workspace}/{skill.skill_id} -> {targets}")
    click.echo(f"wrote {len(written)} files")
