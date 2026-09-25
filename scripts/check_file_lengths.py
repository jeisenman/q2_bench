"""Reject maintainable project files longer than the repository limit."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

MAX_LINES = 400
ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger(__name__)
INCLUDED_SUFFIXES = {
    ".css",
    ".html",
    ".md",
    ".py",
    ".toml",
    ".yaml",
    ".yml",
}
EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "build",
    "dist",
}


def oversized_files(root: Path = ROOT) -> list[tuple[Path, int]]:
    """Return project files that exceed the configured line limit."""
    violations: list[tuple[Path, int]] = []
    for path in root.rglob("*"):
        if (
            not path.is_file()
            or path.suffix not in INCLUDED_SUFFIXES
            or EXCLUDED_PARTS.intersection(path.parts)
        ):
            continue
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > MAX_LINES:
            violations.append((path.relative_to(root), line_count))
    return sorted(violations)


def main() -> int:
    """Run the file-length policy check."""
    parser = argparse.ArgumentParser()
    parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    violations = oversized_files()
    for path, line_count in violations:
        LOGGER.error("%s: %d lines (maximum: %d)", path, line_count, MAX_LINES)
    return int(bool(violations))


if __name__ == "__main__":
    raise SystemExit(main())
