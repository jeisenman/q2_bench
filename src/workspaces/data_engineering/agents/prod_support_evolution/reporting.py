"""Render prompt history as an instructional comparison."""

from workspaces.data_engineering.agents.prod_support_evolution.models import (
    PromptVersion,
)


def render_evolution(versions: tuple[PromptVersion, ...]) -> str:
    """Render chronological versions and lessons as Markdown."""
    sections = ["# Prod-support prompt evolution"]
    for version in versions:
        sections.extend(
            (
                "",
                f"## {version.version}: {version.title}",
                "",
                (
                    f"Commit: `{version.short_commit}` · "
                    f"Date: {version.committed_on.isoformat()}"
                ),
                "",
                version.summary,
                "",
                "Lessons:",
            )
        )
        sections.extend(
            f"- Weakness: {lesson.weakness}\n"
            f"  Improvement: {lesson.improvement}\n"
            f"  Evidence: {lesson.evidence}"
            for lesson in version.lessons
        )
    sections.extend(
        (
            "",
            "## Design pattern",
            "",
            (
                "Improve prompts from observed failures: preserve the failing "
                "example, add the narrowest rule that prevents it, encode "
                "deterministic work in tools, and rerun the same benchmark."
            ),
        )
    )
    return "\n".join(sections)
