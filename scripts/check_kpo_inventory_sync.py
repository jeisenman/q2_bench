"""Verify KPO notebook metadata and retained harness copies."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import NoReturn

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_ROOT = Path("src/workspaces/data_engineering/skills/prod-support")
MIRROR_ROOTS = (
    Path(".codex/skills/prod-support"),
    Path(".claude/skills/prod-support"),
)
PARITY_PATHS = (
    Path("scripts/build_kpo_size_notebook.py"),
    Path("references/kpo-sizing.md"),
    Path("assets/kpo_adls_size_inventory.py"),
)
RELATIONSHIP_JOB = "relationship_signals_time_series_agg_cp_to_snowflake"
VERSION_ROOT_SCOPE = "version_root"


class SyncCheckError(RuntimeError):
    """Report an actionable KPO inventory synchronization failure."""


def _fail(message: str, cause: BaseException | None = None) -> NoReturn:
    if cause is None:
        raise SyncCheckError(message)
    raise SyncCheckError(message) from cause


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        _fail(f"Unable to read {path}: {error}", error)


def _parse_python(path: Path) -> ast.Module:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as error:
        _fail(f"Unable to parse {path}: {error}", error)


def _assignment_value(module: ast.Module, name: str, path: Path) -> ast.expr:
    matches = [
        node.value
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        )
    ]
    if len(matches) != 1:
        _fail(f"Expected one {name} assignment in {path}, found {len(matches)}")
    return matches[0]


def _mapping_rows(value: object, context: str) -> list[dict[object, object]]:
    if not isinstance(value, list):
        _fail(f"Expected a list of rows in {context}")
    rows: list[dict[object, object]] = []
    for index, row in enumerate(value):
        if not isinstance(row, dict):
            _fail(f"Expected mapping row {index} in {context}")
        rows.append(row)
    return rows


def _builder_rows(path: Path) -> list[dict[object, object]]:
    assignment = _assignment_value(_parse_python(path), "JOB_SOURCES", path)
    try:
        value: object = ast.literal_eval(assignment)
    except (TypeError, ValueError) as error:
        _fail(f"JOB_SOURCES is not literal metadata in {path}: {error}", error)
    if not isinstance(value, dict):
        _fail(f"Expected JOB_SOURCES to be a mapping in {path}")

    rows: list[dict[object, object]] = []
    for group_name, group_rows in value.items():
        if not isinstance(group_name, str):
            _fail(f"Expected string JOB_SOURCES keys in {path}")
        rows.extend(_mapping_rows(group_rows, f"{path}:{group_name}"))
    return rows


def _asset_rows(path: Path) -> list[dict[object, object]]:
    assignment = _assignment_value(_parse_python(path), "INVENTORY", path)
    if (
        not isinstance(assignment, ast.Call)
        or not isinstance(assignment.func, ast.Attribute)
        or not isinstance(assignment.func.value, ast.Name)
        or assignment.func.value.id != "json"
        or assignment.func.attr != "loads"
        or len(assignment.args) != 1
        or assignment.keywords
    ):
        _fail(f"Expected INVENTORY = json.loads(<constant>) in {path}")

    try:
        payload: object = ast.literal_eval(assignment.args[0])
    except (TypeError, ValueError) as error:
        _fail(f"INVENTORY is not a constant JSON string in {path}: {error}", error)
    if not isinstance(payload, str):
        _fail(f"Expected a constant INVENTORY JSON string in {path}")
    try:
        inventory: object = json.loads(payload)
    except json.JSONDecodeError as error:
        _fail(f"Invalid INVENTORY JSON in {path}: {error}", error)
    return _mapping_rows(inventory, f"{path}:INVENTORY")


def _assert_version_root_row(
    rows: list[dict[object, object]],
    context: Path,
) -> None:
    matches = [row for row in rows if row.get("job") == RELATIONSHIP_JOB]
    if len(matches) != 1:
        _fail(f"Expected one {RELATIONSHIP_JOB} row in {context}, found {len(matches)}")
    scope = matches[0].get("historical_scope")
    if scope != VERSION_ROOT_SCOPE:
        _fail(
            f"Expected historical_scope={VERSION_ROOT_SCOPE!r} for "
            f"{RELATIONSHIP_JOB} in {context}, found {scope!r}"
        )


def _assert_byte_parity() -> None:
    for relative_path in PARITY_PATHS:
        canonical = REPOSITORY_ROOT / CANONICAL_ROOT / relative_path
        canonical_bytes = _read_bytes(canonical)
        for mirror_root in MIRROR_ROOTS:
            mirror = REPOSITORY_ROOT / mirror_root / relative_path
            if _read_bytes(mirror) != canonical_bytes:
                _fail(
                    f"{mirror.relative_to(REPOSITORY_ROOT)} differs from "
                    f"{canonical.relative_to(REPOSITORY_ROOT)}"
                )


def main() -> int:
    """Check KPO builder, reference, asset, and historical-scope parity."""
    _assert_byte_parity()

    builder = REPOSITORY_ROOT / CANONICAL_ROOT / PARITY_PATHS[0]
    _assert_version_root_row(_builder_rows(builder), builder)

    asset_relative = PARITY_PATHS[2]
    for skill_root in (CANONICAL_ROOT, *MIRROR_ROOTS):
        asset = REPOSITORY_ROOT / skill_root / asset_relative
        _assert_version_root_row(_asset_rows(asset), asset)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
