"""Build reviewable benchmark cases from captured harness traces.

A trace records what a workflow actually did: which tools it called, with what
arguments, and what came back. That is the only trustworthy source for a new
case. This module turns one trace into evidence, mixes in plausible irrelevant
records so the case rewards discrimination rather than recall, and marks every
observed behavior as a candidate expectation pending human review.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Protocol

CANDIDATE_STATUS: Final = "candidate_expectation"
REDACTED: Final = "[redacted]"
SECRET_HINTS: Final = (
    "credential",
    "key",
    "passphrase",
    "password",
    "secret",
    "token",
)
DISTRACTOR_KINDS: Final = (
    "neighbouring_dag",
    "healthy_cluster",
    "unrelated_client",
    "different_failure_reason",
)


class TraceCaseError(ValueError):
    """Raised when a trace cannot produce a trustworthy benchmark case."""

    @classmethod
    def empty_trace(cls, trace_id: str) -> TraceCaseError:
        """Create an error for a trace with no recorded tool calls."""
        return cls(
            f"trace {trace_id!r} recorded no tool calls; "
            "a case needs observed behavior, not an empty run"
        )

    @classmethod
    def negative_distractors(cls, count: int) -> TraceCaseError:
        """Create an error for an impossible distractor count."""
        return cls(f"distractor count must not be negative; got {count}")

    @classmethod
    def naive_capture_time(cls, trace_id: str) -> TraceCaseError:
        """Create an error for a capture timestamp without a timezone."""
        return cls(f"trace {trace_id!r} captured_at must include a timezone")


@dataclass(frozen=True, slots=True)
class RecordedToolCall:
    """One tool invocation preserved from a trace, in call order."""

    ordinal: int
    tool: str
    arguments: Mapping[str, str]
    outcome: str

    def redacted(self) -> RecordedToolCall:
        """Return a copy with secret-shaped argument values removed."""
        return RecordedToolCall(
            ordinal=self.ordinal,
            tool=self.tool,
            arguments={
                name: (REDACTED if _is_secret(name) else value)
                for name, value in sorted(self.arguments.items())
            },
            outcome=self.outcome,
        )


@dataclass(frozen=True, slots=True)
class RecordedTrace:
    """One captured harness run."""

    trace_id: str
    workflow: str
    captured_at: datetime
    tool_calls: tuple[RecordedToolCall, ...]


class TraceSource(Protocol):
    """Read one captured trace without coupling to a tracking product."""

    async def get_trace(self, trace_id: str) -> RecordedTrace:
        """Return one recorded trace or raise when it is unavailable."""
        ...


@dataclass(frozen=True, slots=True)
class Distractor:
    """One plausible but irrelevant record mixed into a case."""

    identifier: str
    kind: str
    tool: str
    detail: str


@dataclass(frozen=True, slots=True)
class TraceCase:
    """A review-required case extracted from one trace."""

    case_id: str
    trace_id: str
    workflow: str
    captured_at: datetime
    evidence: tuple[RecordedToolCall, ...]
    distractors: tuple[Distractor, ...]

    @property
    def tool_counts(self) -> Mapping[str, int]:
        """Return preserved call counts per tool, for the review summary."""
        counts: dict[str, int] = {}
        for call in self.evidence:
            counts[call.tool] = counts.get(call.tool, 0) + 1
        return dict(sorted(counts.items()))

    def as_case_document(self) -> dict[str, Any]:
        """Render the public case file the agent under evaluation may read."""
        return {
            "schema_version": 1,
            "id": self.case_id,
            "status": "captured",
            "review_required": True,
            "source": {
                "trace_id": self.trace_id,
                "workflow": self.workflow,
                "captured_at": self.captured_at.isoformat(),
            },
            "evidence": [
                {
                    "ordinal": call.ordinal,
                    "tool": call.tool,
                    "arguments": dict(call.arguments),
                }
                for call in self.evidence
            ],
            "distractors": [
                {
                    "identifier": item.identifier,
                    "kind": item.kind,
                    "tool": item.tool,
                    "detail": item.detail,
                }
                for item in self.distractors
            ],
            "prohibit_raw_logs": True,
        }

    def as_expectation_document(self) -> dict[str, Any]:
        """Render observed behavior as a candidate requiring human review."""
        return {
            "schema_version": 1,
            "status": CANDIDATE_STATUS,
            "requires_independent_review": True,
            "trace_id": self.trace_id,
            "tool_counts": dict(self.tool_counts),
            "relevant_evidence": [call.ordinal for call in self.evidence],
            "irrelevant_identifiers": [item.identifier for item in self.distractors],
            "observed_outcomes": [
                {"ordinal": call.ordinal, "tool": call.tool, "outcome": call.outcome}
                for call in self.evidence
            ],
        }


def build_trace_case(
    trace: RecordedTrace,
    *,
    distractor_count: int = 0,
) -> TraceCase:
    """Extract one case from a trace and inject deterministic distractors."""
    if distractor_count < 0:
        raise TraceCaseError.negative_distractors(distractor_count)
    if not trace.tool_calls:
        raise TraceCaseError.empty_trace(trace.trace_id)
    if trace.captured_at.tzinfo is None:
        raise TraceCaseError.naive_capture_time(trace.trace_id)
    evidence = tuple(call.redacted() for call in trace.tool_calls)
    return TraceCase(
        case_id=_case_id(trace),
        trace_id=trace.trace_id,
        workflow=trace.workflow,
        captured_at=trace.captured_at,
        evidence=evidence,
        distractors=build_distractors(evidence, distractor_count, trace.trace_id),
    )


def build_distractors(
    evidence: Sequence[RecordedToolCall],
    count: int,
    seed: str,
) -> tuple[Distractor, ...]:
    """Derive plausible irrelevant records from the observed tool calls.

    Distractors are derived from real evidence so they stay plausible for the
    same operational window, and are derived deterministically so a case can be
    rebuilt and reviewed without drift. Identifiers are prefixed so a reviewer
    can always separate injected noise from captured signal.
    """
    if count < 0:
        raise TraceCaseError.negative_distractors(count)
    if not evidence:
        return ()
    distractors: list[Distractor] = []
    for index in range(count):
        source = evidence[index % len(evidence)]
        kind = DISTRACTOR_KINDS[index % len(DISTRACTOR_KINDS)]
        digest = hashlib.sha256(
            f"{seed}:{index}:{source.tool}:{kind}".encode()
        ).hexdigest()[:10]
        distractors.append(
            Distractor(
                identifier=f"distractor-{digest}",
                kind=kind,
                tool=source.tool,
                detail=_distractor_detail(kind, source),
            )
        )
    return tuple(distractors)


def _distractor_detail(kind: str, source: RecordedToolCall) -> str:
    details = {
        "neighbouring_dag": (
            f"A different DAG in the same window that {source.tool} can also "
            "return, unrelated to the reported symptom."
        ),
        "healthy_cluster": (
            "A cluster reporting healthy for the same window; correct handling "
            "is to exclude it from findings."
        ),
        "unrelated_client": (
            "A client present in the same window whose resources are unaffected."
        ),
        "different_failure_reason": (
            "A failure in the same window with an unrelated root cause; it must "
            "not be grouped with the reported failure."
        ),
    }
    return details[kind]


def _case_id(trace: RecordedTrace) -> str:
    workflow = re.sub(r"[^a-z0-9]+", "-", trace.workflow.casefold()).strip("-")
    date = trace.captured_at.date().isoformat()
    return f"{workflow or 'workflow'}-{date}-{trace.trace_id[:8]}"


def _is_secret(name: str) -> bool:
    normalized = name.casefold()
    return any(hint in normalized for hint in SECRET_HINTS)
