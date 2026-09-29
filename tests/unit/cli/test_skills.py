from pathlib import Path

import yaml
from click.testing import CliRunner

from cli.skills import sync_skills

MANIFEST = {
    "schema_version": 1,
    "id": "demo",
    "workspace": "data_engineering",
    "display_name": "Demo",
    "summary": "A demo skill.",
    "harnesses": ["claude", "codex"],
}


def write_skill(root: Path) -> Path:
    directory = root / "src/workspaces/data_engineering/skills/demo"
    directory.mkdir(parents=True)
    (directory / "skill.yaml").write_text(yaml.safe_dump(MANIFEST), encoding="utf-8")
    (directory / "SKILL.md").write_text("Use {{SKILL_DIR}}/go.py\n", encoding="utf-8")
    return directory


def invoke(root: Path, *args: str):
    return CliRunner().invoke(
        sync_skills,
        [
            "--workspaces-root",
            str(root / "src/workspaces"),
            "--project-root",
            str(root),
            *args,
        ],
    )


def test_sync_reports_each_skill_and_its_harnesses(tmp_path: Path) -> None:
    write_skill(tmp_path)

    result = invoke(tmp_path)

    assert result.exit_code == 0
    assert "data_engineering/demo -> .claude/skills, .codex/skills" in result.output
    assert (tmp_path / ".claude/skills/demo/SKILL.md").is_file()
    assert (tmp_path / ".codex/skills/demo/SKILL.md").is_file()


def test_check_passes_on_a_current_tree(tmp_path: Path) -> None:
    write_skill(tmp_path)
    invoke(tmp_path)

    result = invoke(tmp_path, "--check")

    assert result.exit_code == 0
    assert "are current" in result.output


def test_check_fails_and_names_the_fix_when_a_copy_is_edited(tmp_path: Path) -> None:
    write_skill(tmp_path)
    invoke(tmp_path)
    (tmp_path / ".claude/skills/demo/SKILL.md").write_text("edited\n", encoding="utf-8")

    result = invoke(tmp_path, "--check")

    assert result.exit_code != 0
    assert "stale" in result.output
    assert "agentbench sync-skills" in result.output


def test_missing_skills_directory_fails_fast(tmp_path: Path) -> None:
    (tmp_path / "src/workspaces").mkdir(parents=True)

    result = invoke(tmp_path)

    assert result.exit_code != 0
    assert "no skills found" in result.output
