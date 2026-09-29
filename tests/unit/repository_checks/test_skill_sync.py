from pathlib import Path

import pytest
import yaml

from repository_checks.skill_sync import (
    SkillSyncError,
    apply_plan,
    discover_skills,
    plan_sync,
    stale_targets,
)

MANIFEST = {
    "schema_version": 1,
    "id": "demo",
    "workspace": "data_engineering",
    "display_name": "Demo",
    "summary": "A demo skill.",
    "harnesses": ["claude", "codex"],
}


def write_skill(root: Path, manifest: dict[str, object] | None = None) -> Path:
    directory = root / "src/workspaces/data_engineering/skills/demo"
    (directory / "scripts").mkdir(parents=True)
    (directory / "harness/codex").mkdir(parents=True)
    (directory / "skill.yaml").write_text(
        yaml.safe_dump(manifest or MANIFEST), encoding="utf-8"
    )
    (directory / "SKILL.md").write_text(
        "Run python3 {{SKILL_DIR}}/scripts/go.py\n", encoding="utf-8"
    )
    (directory / "scripts/go.py").write_text("print('go')\n", encoding="utf-8")
    (directory / "harness/codex/openai.yaml").write_text(
        "interface: {}\n", encoding="utf-8"
    )
    return directory


def sync(root: Path):
    skills = discover_skills(root / "src/workspaces")
    plan = plan_sync(root, skills)
    apply_plan(root, plan)
    return plan


def test_sync_renders_each_harness_with_its_own_skill_path(tmp_path: Path) -> None:
    write_skill(tmp_path)
    sync(tmp_path)

    claude = tmp_path / ".claude/skills/demo/SKILL.md"
    codex = tmp_path / ".codex/skills/demo/SKILL.md"
    assert ".claude/skills/demo/scripts/go.py" in claude.read_text(encoding="utf-8")
    assert ".codex/skills/demo/scripts/go.py" in codex.read_text(encoding="utf-8")


def test_harness_overlay_reaches_only_its_own_harness(tmp_path: Path) -> None:
    write_skill(tmp_path)
    sync(tmp_path)

    assert (tmp_path / ".codex/skills/demo/openai.yaml").is_file()
    assert not (tmp_path / ".claude/skills/demo/openai.yaml").exists()


def test_manifest_is_not_copied_into_harness_directories(tmp_path: Path) -> None:
    write_skill(tmp_path)
    sync(tmp_path)

    assert not (tmp_path / ".claude/skills/demo/skill.yaml").exists()


def test_python_bytecode_cache_is_not_copied(tmp_path: Path) -> None:
    directory = write_skill(tmp_path)
    cache = directory / "scripts/__pycache__"
    cache.mkdir()
    (cache / "go.cpython-311.pyc").write_bytes(b"\xa7")

    sync(tmp_path)

    assert not (tmp_path / ".claude/skills/demo/scripts/__pycache__").exists()


def test_check_reports_stale_and_unmanaged_files(tmp_path: Path) -> None:
    write_skill(tmp_path)
    plan = sync(tmp_path)
    assert stale_targets(tmp_path, plan) == ()

    edited = tmp_path / ".claude/skills/demo/SKILL.md"
    edited.write_text("hand edited\n", encoding="utf-8")
    (tmp_path / ".codex/skills/demo/stray.md").write_text("stray\n", encoding="utf-8")

    problems = stale_targets(tmp_path, plan)
    assert any("stale" in problem for problem in problems)
    assert any("not generated" in problem for problem in problems)


def test_missing_generated_file_is_reported(tmp_path: Path) -> None:
    write_skill(tmp_path)
    plan = sync(tmp_path)
    (tmp_path / ".claude/skills/demo/scripts/go.py").unlink()

    assert any("missing" in problem for problem in stale_targets(tmp_path, plan))


def test_declared_state_survives_resync_and_is_not_drift(tmp_path: Path) -> None:
    manifest = dict(MANIFEST) | {"state": ["references/data.json"]}
    directory = write_skill(tmp_path, manifest)
    (directory / "references").mkdir()
    (directory / "references/data.json").write_text("{}\n", encoding="utf-8")

    sync(tmp_path)
    runtime = tmp_path / ".codex/skills/demo/references/data.json"
    runtime.write_text('{"written":"by harness"}\n', encoding="utf-8")

    plan = sync(tmp_path)
    assert runtime.read_text(encoding="utf-8") == '{"written":"by harness"}\n'
    assert stale_targets(tmp_path, plan) == ()


def test_unknown_harness_is_rejected(tmp_path: Path) -> None:
    write_skill(tmp_path, dict(MANIFEST) | {"harnesses": ["gemini"]})

    with pytest.raises(SkillSyncError, match="unknown harness"):
        discover_skills(tmp_path / "src/workspaces")


def test_id_must_match_directory_name(tmp_path: Path) -> None:
    write_skill(tmp_path, dict(MANIFEST) | {"id": "other"})

    with pytest.raises(SkillSyncError, match="must match directory"):
        discover_skills(tmp_path / "src/workspaces")


def test_missing_required_manifest_field_is_rejected(tmp_path: Path) -> None:
    manifest = {key: value for key, value in MANIFEST.items() if key != "summary"}
    write_skill(tmp_path, manifest)

    with pytest.raises(SkillSyncError, match="missing required fields: summary"):
        discover_skills(tmp_path / "src/workspaces")


def test_skill_without_document_is_rejected(tmp_path: Path) -> None:
    directory = write_skill(tmp_path)
    (directory / "SKILL.md").unlink()

    with pytest.raises(SkillSyncError, match=r"missing SKILL\.md"):
        discover_skills(tmp_path / "src/workspaces")


def test_duplicate_skill_id_across_workspaces_is_rejected(tmp_path: Path) -> None:
    write_skill(tmp_path)
    other = tmp_path / "src/workspaces/platform/skills/demo"
    other.mkdir(parents=True)
    (other / "skill.yaml").write_text(
        yaml.safe_dump(dict(MANIFEST) | {"workspace": "platform"}), encoding="utf-8"
    )
    (other / "SKILL.md").write_text("other\n", encoding="utf-8")

    with pytest.raises(SkillSyncError, match="duplicate skill id"):
        discover_skills(tmp_path / "src/workspaces")


def test_sync_preserves_unmanaged_entries_in_a_harness_root(tmp_path: Path) -> None:
    # A harness skills root can hold skills this repository does not generate,
    # such as a symlink to a skill owned by a sibling repository. Syncing must
    # not delete them, and drift reporting must not flag them.
    write_skill(tmp_path)
    sync(tmp_path)

    external = tmp_path / "external-skill"
    external.mkdir()
    (external / "SKILL.md").write_text("external\n", encoding="utf-8")
    linked = tmp_path / ".codex/skills/borrowed"
    linked.symlink_to(external, target_is_directory=True)

    plan = sync(tmp_path)

    assert linked.is_symlink()
    assert (linked / "SKILL.md").read_text(encoding="utf-8") == "external\n"
    assert stale_targets(tmp_path, plan) == ()


def test_non_mapping_manifest_is_rejected(tmp_path: Path) -> None:
    directory = write_skill(tmp_path)
    (directory / "skill.yaml").write_text("- not a mapping\n", encoding="utf-8")

    with pytest.raises(SkillSyncError, match="must be a mapping"):
        discover_skills(tmp_path / "src/workspaces")


def test_unsupported_schema_version_is_rejected(tmp_path: Path) -> None:
    write_skill(tmp_path, dict(MANIFEST) | {"schema_version": 2})

    with pytest.raises(SkillSyncError, match="schema_version must be 1"):
        discover_skills(tmp_path / "src/workspaces")


def test_empty_harness_list_is_rejected(tmp_path: Path) -> None:
    write_skill(tmp_path, dict(MANIFEST) | {"harnesses": []})

    with pytest.raises(SkillSyncError, match="non-empty list"):
        discover_skills(tmp_path / "src/workspaces")


def test_non_list_state_is_rejected(tmp_path: Path) -> None:
    write_skill(tmp_path, dict(MANIFEST) | {"state": "references/data.json"})

    with pytest.raises(SkillSyncError, match="state must be a list"):
        discover_skills(tmp_path / "src/workspaces")


def test_skill_directory_without_manifest_is_ignored(tmp_path: Path) -> None:
    write_skill(tmp_path)
    stray = tmp_path / "src/workspaces/data_engineering/skills/no-manifest"
    stray.mkdir(parents=True)
    (stray / "SKILL.md").write_text("orphan\n", encoding="utf-8")

    assert [
        skill.skill_id for skill in discover_skills(tmp_path / "src/workspaces")
    ] == ["demo"]


def test_overlay_for_another_harness_is_skipped(tmp_path: Path) -> None:
    directory = write_skill(tmp_path, dict(MANIFEST) | {"harnesses": ["claude"]})
    (directory / "harness/codex/openai.yaml").write_text("x: 1\n", encoding="utf-8")
    sync(tmp_path)

    assert not (tmp_path / ".claude/skills/demo/openai.yaml").exists()
    assert not (tmp_path / ".codex/skills/demo").exists()
