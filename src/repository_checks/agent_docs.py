"""Validate required architecture documentation for agent packages."""

from pathlib import Path
from typing import Final

REQUIRED_SECTIONS: Final = (
    "Architecture",
    "Dependencies",
    "Workflow",
)
PLACEHOLDERS: Final = ("todo", "tbd", "<agent name>")


def find_errors(agents_root: Path) -> tuple[str, ...]:
    """Return documentation policy violations beneath an agents directory."""
    errors: list[str] = []
    packages = sorted(
        path.parent for path in agents_root.glob("*/__init__.py") if path.is_file()
    )
    for package in packages:
        document = package / "AGENTS.md"
        if not document.is_file():
            errors.append(f"{package}: missing AGENTS.md")
            continue

        content = document.read_text(encoding="utf-8")
        normalized = content.casefold()
        for section in REQUIRED_SECTIONS:
            heading = f"## {section}"
            if heading not in content:
                errors.append(f"{document}: missing '{heading}' section")
        if any(placeholder in normalized for placeholder in PLACEHOLDERS):
            errors.append(f"{document}: contains placeholder content")
    return tuple(errors)
