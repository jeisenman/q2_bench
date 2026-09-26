"""Tests for the agent documentation policy check."""

from pathlib import Path

from repository_checks.agent_docs import find_errors


def test_find_errors_accepts_required_documentation(tmp_path: Path) -> None:
    """A documented agent satisfies the policy."""
    package = tmp_path / "example"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "AGENTS.md").write_text(
        "# Example\n\n## Architecture\n\nEntry point.\n\n"
        "## Dependencies\n\nNo external services.\n\n"
        "## Workflow\n\nValidate, run, and report.\n",
        encoding="utf-8",
    )

    assert find_errors(tmp_path) == ()


def test_find_errors_reports_missing_document(tmp_path: Path) -> None:
    """An agent package without AGENTS.md fails the policy."""
    package = tmp_path / "example"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")

    assert find_errors(tmp_path) == (f"{package}: missing AGENTS.md",)


def test_find_errors_reports_missing_sections_and_placeholders(
    tmp_path: Path,
) -> None:
    """Incomplete template content fails with actionable errors."""
    package = tmp_path / "example"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    document = package / "AGENTS.md"
    document.write_text("# Example\n\n## Architecture\n\nTBD\n", encoding="utf-8")

    assert find_errors(tmp_path) == (
        f"{document}: missing '## Dependencies' section",
        f"{document}: missing '## Workflow' section",
        f"{document}: contains placeholder content",
    )
