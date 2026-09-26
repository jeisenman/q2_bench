"""Load public benchmark cases with evaluator-only expectations."""

from pathlib import Path
from typing import Any

import yaml


def load_case_with_expectations(cases_path: Path, case_id: str) -> dict[str, Any]:
    """Merge one public case with its sibling hidden expectation record."""
    public = _find_case(_load_mapping(cases_path), case_id)
    hidden_path = cases_path.parent / "hidden/case_expectations.yaml"
    if not hidden_path.is_file():
        return public
    hidden_root = _load_mapping(hidden_path)
    hidden = (
        _find_case(hidden_root, case_id)
        if isinstance(hidden_root.get("cases"), list)
        else hidden_root
    )
    if hidden.get("case_id", case_id) != case_id:
        return public
    return {**public, **hidden, "id": case_id}


def _load_mapping(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        message = f"{path}: expected a mapping"
        raise TypeError(message)
    return raw


def _find_case(root: dict[str, Any], case_id: str) -> dict[str, Any]:
    cases = root.get("cases")
    if not isinstance(cases, list):
        message = "cases must be a list"
        raise TypeError(message)
    selected = next(
        (
            item
            for item in cases
            if isinstance(item, dict) and item.get("id") == case_id
        ),
        None,
    )
    if selected is None:
        message = f"Unknown benchmark case: {case_id}"
        raise KeyError(message)
    return dict(selected)
