"""Compact exact task logs without losing diagnostic evidence."""

from __future__ import annotations

from dataclasses import dataclass

from workspaces.data_engineering.agents.prod_support.models import EvidenceStatus

DEFAULT_EVIDENCE_LINES = 3
DEFAULT_EVIDENCE_CHARACTERS = 1_200
TERMINAL_MARKERS = (
    "airflowtasktimeout",
    "distinctness",
    "exception",
    "exit -9",
    "exit code -9",
    "failed",
    "oomkilled",
    "outofmemoryerror",
    "sigkill",
    "traceback",
)
TRUNCATION_MARKERS = ("log truncated", "truncated log", "was not found in the log")
COUNT_MARKERS = ("missing opportunity", "unique events", "unique missing")


@dataclass(frozen=True, slots=True)
class TaskLogSummary:
    """Bounded evidence retained from one exact task-attempt log."""

    status: EvidenceStatus
    original_char_count: int
    excerpt: str


def summarize_task_log(
    log: str,
    *,
    max_lines: int = DEFAULT_EVIDENCE_LINES,
    max_characters: int = DEFAULT_EVIDENCE_CHARACTERS,
) -> TaskLogSummary:
    """Select diagnostic lines and omit the remaining raw log body."""
    if max_lines < 1:
        message = "max_lines must be positive"
        raise ValueError(message)
    if max_characters < 1:
        message = "max_characters must be positive"
        raise ValueError(message)
    normalized = log.replace("\\n", "\n")
    lines = tuple(line.strip() for line in normalized.splitlines() if line.strip())
    lowered = tuple(line.lower() for line in lines)
    relevant = tuple(
        line
        for line, lower in zip(lines, lowered, strict=True)
        if any(marker in lower for marker in (*TERMINAL_MARKERS, *COUNT_MARKERS))
    )
    selected = (relevant or lines[-max_lines:])[:max_lines]
    excerpt = "\n".join(selected)[:max_characters]
    if any(marker in normalized.lower() for marker in TRUNCATION_MARKERS):
        status = EvidenceStatus.TRUNCATED
    elif relevant:
        status = EvidenceStatus.TERMINAL
    else:
        status = EvidenceStatus.NON_DIAGNOSTIC
    return TaskLogSummary(status, len(log), excerpt)
