"""Materialize workspace-owned skills into harness skill directories.

A workspace owns its skills. Each harness discovers skills from its own
directory, so the workspace tree is the single source of truth and the harness
trees are generated. ``plan_sync`` is pure; ``apply_plan`` performs the writes
and ``stale_targets`` reports drift for the repository quality gate.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import yaml

SKILL_MANIFEST: Final = "skill.yaml"
SKILL_DOCUMENT: Final = "SKILL.md"
HARNESS_DIRECTORY: Final = "harness"
SYNC_MANIFEST: Final = ".skill-sync.json"
SKILL_DIR_TOKEN: Final = "{{SKILL_DIR}}"
SKILLS_ROOT_TOKEN: Final = "{{SKILLS_ROOT}}"
TEMPLATED_SUFFIXES: Final = frozenset({".md", ".yaml", ".yml"})
HARNESS_PATH_DEPTH: Final = 2
HARNESS_ROOTS: Final[Mapping[str, str]] = {
    "claude": ".claude/skills",
    "codex": ".codex/skills",
}
REQUIRED_MANIFEST_FIELDS: Final = frozenset(
    {"schema_version", "id", "workspace", "display_name", "summary", "harnesses"}
)


class SkillSyncError(RuntimeError):
    """Raised when workspace skills cannot be synced safely."""

    @classmethod
    def unknown_harness(cls, skill_id: str, harness: str) -> SkillSyncError:
        """Create an error for an unsupported harness name."""
        supported = ", ".join(sorted(HARNESS_ROOTS))
        return cls(
            f"skill {skill_id!r} targets unknown harness {harness!r}; "
            f"supported harnesses: {supported}"
        )

    @classmethod
    def missing_manifest(cls, directory: Path) -> SkillSyncError:
        """Create an error for a skill directory without a manifest."""
        return cls(f"{directory}: missing {SKILL_MANIFEST}")

    @classmethod
    def missing_document(cls, directory: Path) -> SkillSyncError:
        """Create an error for a skill directory without a skill document."""
        return cls(f"{directory}: missing {SKILL_DOCUMENT}")

    @classmethod
    def invalid_manifest(cls, path: Path, reason: str) -> SkillSyncError:
        """Create an error identifying a manifest and validation reason."""
        return cls(f"{path}: {reason}")

    @classmethod
    def duplicate_skill(
        cls,
        skill_id: str,
        first: Path,
        second: Path,
    ) -> SkillSyncError:
        """Create an error for two workspaces exporting one skill name."""
        return cls(
            f"duplicate skill id {skill_id!r} exported by {first} and {second}; "
            "harness skill directories are flat, so ids must be globally unique"
        )


@dataclass(frozen=True, slots=True)
class Skill:
    """One workspace-owned skill and the harnesses that should receive it."""

    skill_id: str
    workspace: str
    source: Path
    harnesses: tuple[str, ...]
    state: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SyncedFile:
    """One generated harness file and the digest of its rendered content."""

    target: Path
    content: str
    digest: str
    is_state: bool = False


@dataclass(frozen=True, slots=True)
class SyncPlan:
    """Every harness file implied by the current workspace skill tree."""

    files: tuple[SyncedFile, ...]
    roots: tuple[Path, ...]
    managed: tuple[Path, ...]

    def manifest(self, project_root: Path) -> str:
        """Render the sync manifest recording generated paths and digests."""
        return (
            json.dumps(
                {
                    "schema_version": 1,
                    "generated_from": "src/workspaces/*/skills",
                    "files": {
                        _display_path(item.target, project_root): item.digest
                        for item in sorted(self.files, key=lambda item: item.target)
                        if not item.is_state
                    },
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )


def discover_skills(workspaces_root: Path) -> tuple[Skill, ...]:
    """Load every skill manifest beneath ``<workspaces_root>/*/skills``."""
    skills: dict[str, Skill] = {}
    for manifest_path in sorted(workspaces_root.glob("*/skills/*/" + SKILL_MANIFEST)):
        skill = _load_skill(manifest_path)
        existing = skills.get(skill.skill_id)
        if existing is not None:
            raise SkillSyncError.duplicate_skill(
                skill.skill_id, existing.source, skill.source
            )
        skills[skill.skill_id] = skill
    return tuple(skills.values())


def global_harness_roots() -> Mapping[str, Path]:
    """Return the user-level skill directories for the supported harnesses."""
    claude_config = Path(
        os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))
    ).expanduser()
    codex_config = Path(
        os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))
    ).expanduser()
    return {
        "claude": claude_config / "skills",
        "codex": codex_config / "skills",
    }


def plan_sync(
    project_root: Path,
    skills: Iterable[Skill],
    harness_roots: Mapping[str, Path | str] | None = None,
) -> SyncPlan:
    """Render every harness file without touching the filesystem."""
    roots_by_harness = harness_roots or HARNESS_ROOTS
    files: list[SyncedFile] = []
    roots: set[Path] = set()
    managed: set[Path] = set()
    for skill in skills:
        for harness in skill.harnesses:
            configured_root = roots_by_harness[harness]
            skills_root_path = _resolve_root(project_root, configured_root)
            root = skills_root_path / skill.skill_id
            roots.add(skills_root_path)
            managed.add(root)
            skills_root = _render_root_path(
                skills_root_path,
                configured_root,
                project_root,
            )
            skill_dir = f"{skills_root}/{skill.skill_id}"
            files.extend(_render_skill(skill, harness, root, skill_dir, skills_root))
    return SyncPlan(
        files=tuple(sorted(files, key=lambda item: item.target)),
        roots=tuple(sorted(roots)),
        managed=tuple(sorted(managed)),
    )


def apply_plan(project_root: Path, plan: SyncPlan) -> tuple[Path, ...]:
    """Replace generated harness trees with the planned content."""
    preserved = {
        item.target: item.target.read_text(encoding="utf-8")
        for item in plan.files
        if item.is_state and item.target.is_file()
    }
    for directory in plan.managed:
        if directory.is_dir() and not directory.is_symlink():
            shutil.rmtree(directory)
        directory.mkdir(parents=True, exist_ok=True)
    for root in plan.roots:
        root.mkdir(parents=True, exist_ok=True)
    for target, content in preserved.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    for item in plan.files:
        item.target.parent.mkdir(parents=True, exist_ok=True)
        if item.is_state and item.target.exists():
            continue
        item.target.write_text(item.content, encoding="utf-8")
    written = [item.target for item in plan.files]
    for root in plan.roots:
        manifest_path = root / SYNC_MANIFEST
        manifest_path.write_text(plan.manifest(project_root), encoding="utf-8")
        written.append(manifest_path)
    return tuple(sorted(written))


def stale_targets(project_root: Path, plan: SyncPlan) -> tuple[str, ...]:
    """Return human-readable drift between the workspace and harness trees."""
    problems: list[str] = []
    state = {item.target for item in plan.files if item.is_state}
    expected = {item.target: item.digest for item in plan.files if not item.is_state}
    for target, digest in sorted(expected.items()):
        relative = _display_path(target, project_root)
        if not target.is_file():
            problems.append(f"{relative}: missing; run 'agentbench sync-skills'")
            continue
        actual = _digest(target.read_text(encoding="utf-8"))
        if actual != digest:
            problems.append(f"{relative}: stale; run 'agentbench sync-skills'")
    for directory in plan.managed:
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.name == SYNC_MANIFEST:
                continue
            if path not in expected and path not in state:
                relative = _display_path(path, project_root)
                problems.append(
                    f"{relative}: not generated from its workspace skill source; "
                    "move it into the workspace skill directory"
                )
    return tuple(problems)


def _load_skill(manifest_path: Path) -> Skill:
    directory = manifest_path.parent
    if not (directory / SKILL_DOCUMENT).is_file():
        raise SkillSyncError.missing_document(directory)
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SkillSyncError.invalid_manifest(
            manifest_path, "manifest must be a mapping"
        )
    missing = REQUIRED_MANIFEST_FIELDS.difference(raw)
    if missing:
        fields = ", ".join(sorted(missing))
        raise SkillSyncError.invalid_manifest(
            manifest_path, f"missing required fields: {fields}"
        )
    if raw["schema_version"] != 1:
        raise SkillSyncError.invalid_manifest(manifest_path, "schema_version must be 1")
    skill_id = str(raw["id"])
    if skill_id != directory.name:
        raise SkillSyncError.invalid_manifest(
            manifest_path, f"id {skill_id!r} must match directory {directory.name!r}"
        )
    harnesses = raw["harnesses"]
    if not isinstance(harnesses, list) or not harnesses:
        raise SkillSyncError.invalid_manifest(
            manifest_path, "harnesses must be a non-empty list"
        )
    for harness in harnesses:
        if harness not in HARNESS_ROOTS:
            raise SkillSyncError.unknown_harness(skill_id, str(harness))
    raw_state = raw.get("state", [])
    if not isinstance(raw_state, list):
        raise SkillSyncError.invalid_manifest(
            manifest_path, "state must be a list of skill-relative paths"
        )
    return Skill(
        skill_id=skill_id,
        workspace=str(raw["workspace"]),
        source=directory,
        harnesses=tuple(str(harness) for harness in harnesses),
        state=tuple(str(item) for item in raw_state),
    )


def _render_skill(
    skill: Skill,
    harness: str,
    root: Path,
    skill_dir: str,
    skills_root: str,
) -> tuple[SyncedFile, ...]:
    rendered: list[SyncedFile] = []
    for path in sorted(skill.source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(skill.source)
        if "__pycache__" in relative.parts or path.suffix == ".pyc":
            continue
        if relative.parts[0] == HARNESS_DIRECTORY:
            if len(relative.parts) < HARNESS_PATH_DEPTH or relative.parts[1] != harness:
                continue
            relative = Path(*relative.parts[HARNESS_PATH_DEPTH:])
        if relative.name == SKILL_MANIFEST:
            continue
        content = path.read_text(encoding="utf-8")
        if path.suffix in TEMPLATED_SUFFIXES:
            content = content.replace(SKILL_DIR_TOKEN, skill_dir)
            content = content.replace(SKILLS_ROOT_TOKEN, skills_root)
        rendered.append(
            SyncedFile(
                target=root / relative,
                content=content,
                digest=_digest(content),
                is_state=relative.as_posix() in skill.state,
            )
        )
    if not (skill.source / SKILL_DOCUMENT).is_file():
        raise SkillSyncError.missing_document(skill.source)
    return tuple(rendered)


def _digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _resolve_root(project_root: Path, root: Path | str) -> Path:
    """Resolve a local or absolute harness skill root."""
    path = Path(root).expanduser()
    return path if path.is_absolute() else project_root / path


def _display_path(path: Path, project_root: Path) -> str:
    """Display paths relative to the project when possible."""
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)


def _render_root_path(
    resolved_root: Path,
    configured_root: Path | str,
    project_root: Path,
) -> str:
    """Render local roots relatively and user-level roots absolutely."""
    if Path(configured_root).expanduser().is_absolute():
        return str(resolved_root)
    return _display_path(resolved_root, project_root)
