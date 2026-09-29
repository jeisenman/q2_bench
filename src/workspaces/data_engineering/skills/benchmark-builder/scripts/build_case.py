#!/usr/bin/env python3
"""Extract a benchmark case from a captured MLflow trace."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import mlflow
import yaml

from workspaces.data_engineering.benchmarks.trace_cases import (
    RecordedToolCall,
    RecordedTrace,
    TraceCaseError,
    build_trace_case,
)


def load_trace(trace_id: str) -> RecordedTrace:
    """Read one trace from the configured MLflow tracking server."""
    trace = mlflow.get_trace(trace_id)
    if trace is None:
        raise TraceCaseError(f"trace {trace_id!r} was not found")
    calls: list[RecordedToolCall] = []
    ordinal = 0
    for span in trace.data.spans:
        if getattr(span, "span_type", None) != "TOOL":
            continue
        ordinal += 1
        inputs = span.inputs if isinstance(span.inputs, dict) else {}
        calls.append(
            RecordedToolCall(
                ordinal=ordinal,
                tool=span.name,
                arguments={str(k): str(v) for k, v in inputs.items()},
                outcome=str(span.outputs)[:500],
            )
        )
    started = getattr(trace.info, "timestamp_ms", None)
    captured = (
        datetime.fromtimestamp(started / 1000, tz=UTC) if started else datetime.now(UTC)
    )
    return RecordedTrace(
        trace_id=trace_id,
        workflow=trace.info.request_metadata.get("workflow", "workflow"),
        captured_at=captured,
        tool_calls=tuple(calls),
    )


def main() -> int:
    """Write a public case file and a candidate expectation file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace_id")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--distractors", type=int, default=0)
    args = parser.parse_args()

    try:
        trace = load_trace(args.trace_id)
        case = build_trace_case(trace, distractor_count=args.distractors)
    except TraceCaseError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "case.yaml").write_text(
        yaml.safe_dump(case.as_case_document(), sort_keys=False), encoding="utf-8"
    )
    (args.output / "expected_behavior.yaml").write_text(
        yaml.safe_dump(case.as_expectation_document(), sort_keys=False),
        encoding="utf-8",
    )
    print(f"case: {case.case_id}")
    print(f"evidence: {sum(case.tool_counts.values())} tool calls")
    for tool, count in case.tool_counts.items():
        print(f"  {tool}: {count}")
    print(f"distractors: {len(case.distractors)}")
    print(f"written to: {args.output}")
    print("review required: expectations are candidates, not truth")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
