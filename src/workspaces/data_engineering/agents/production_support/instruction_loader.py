"""Load versioned production-support agent instructions from Markdown."""

from pathlib import Path

INSTRUCTION_ROOT = Path(__file__).with_name("instructions")


def load_instruction(name: str) -> str:
    """Return one non-empty Markdown instruction document."""
    path = INSTRUCTION_ROOT / f"{name}.md"
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        message = f"production-support instruction is empty: {path}"
        raise ValueError(message)
    return content
