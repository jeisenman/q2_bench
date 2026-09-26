"""Safe persistence helpers for benchmark matrix artifacts."""

from __future__ import annotations

import os
from pathlib import Path

from adapters.inbound.matrix_runtime import MatrixRunError
from adapters.inbound.trace_compaction import redact_text


def _write_output(path: Path, value: str, root: Path) -> None:
    """Write one output without following candidate-created symlinks."""
    _validate_output_path(path, root)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as error:
        message = f"matrix output is not a safe regular file: {path}"
        raise MatrixRunError(message) from error
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(value)


def _read_output(path: Path, root: Path) -> str:
    """Read one candidate output after rejecting symlinks and escapes."""
    _validate_output_path(path, root)
    if not path.is_file() or path.is_symlink():
        message = f"matrix output is not a safe regular file: {path}"
        raise MatrixRunError(message)
    return path.read_text(encoding="utf-8")


def _redact_output(
    path: Path,
    root: Path,
    *,
    required: bool,
) -> str:
    """Redact an output in place, allowing absent files after failed processes."""
    if not path.is_file() and not required:
        return ""
    redacted = redact_text(_read_output(path, root))
    _write_output(path, redacted, root)
    return redacted


def _validate_output_path(path: Path, root: Path) -> None:
    if path.is_symlink():
        message = f"matrix output may not be a symlink: {path}"
        raise MatrixRunError(message)
    try:
        path.parent.resolve().relative_to(root.resolve())
    except ValueError as error:
        message = f"matrix output resolves outside profile root: {path}"
        raise MatrixRunError(message) from error
