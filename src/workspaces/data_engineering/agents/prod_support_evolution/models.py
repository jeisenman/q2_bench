"""Immutable prompt-evolution domain models."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class PromptLesson:
    """Explain one weakness and the rule introduced to address it."""

    weakness: str
    improvement: str
    evidence: str


@dataclass(frozen=True, slots=True)
class PromptVersion:
    """Describe one historical prod-support prompt revision."""

    version: str
    commit: str
    committed_on: date
    title: str
    source_path: str
    summary: str
    lessons: tuple[PromptLesson, ...]

    @property
    def short_commit(self) -> str:
        """Return the conventional abbreviated commit identifier."""
        return self.commit[:8]
