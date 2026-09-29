"""Write review-required daily benchmark drafts from production outcomes.

The delegating BenchBuilder agent is gone; the capture procedure lives in
the benchmark-builder skill and this module only writes the artifacts.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from workspaces.data_engineering.workflows.prod_support.models import (
    ProdSupportOutcome,
)

BENCH_BUILDER_MAX_PARALLEL = 5
CAPTURED_STAGES = (
    "cluster_health",
    "triage",
    "follow_up",
    "reporting",
)


class BenchmarkCaseBuildError(ValueError):
    """Raised when a daily benchmark draft cannot be built safely."""

    @classmethod
    def naive_capture_time(cls) -> BenchmarkCaseBuildError:
        """Create an error for a capture timestamp without a timezone."""
        return cls("captured_at must include a timezone")

    @classmethod
    def unsafe_correlation_id(cls) -> BenchmarkCaseBuildError:
        """Create an error for a correlation ID unusable as a path segment."""
        return cls("correlation_id must contain a safe path character")


@dataclass(frozen=True, slots=True)
class BenchmarkCaseArtifacts:
    """Paths written for one review-required benchmark draft."""

    root: Path
    case: Path
    expected_behavior: Path
    manifest: Path

    def as_dict(self) -> dict[str, object]:
        """Return MCP-safe artifact metadata."""
        return {
            "status": "captured",
            "review_required": True,
            "root": str(self.root),
            "case": str(self.case),
            "expected_behavior": str(self.expected_behavior),
            "manifest": str(self.manifest),
        }


def build_daily_benchmark_case(
    outcome: ProdSupportOutcome,
    prompt: str,
    correlation_id: str,
    output_root: Path,
    *,
    captured_at: datetime | None = None,
) -> BenchmarkCaseArtifacts:
    """Write a non-overwriting benchmark draft without raw task logs."""
    observed_at = captured_at or datetime.now(UTC)
    if observed_at.tzinfo is None:
        raise BenchmarkCaseBuildError.naive_capture_time()
    safe_correlation = re.sub(r"[^a-zA-Z0-9._-]", "-", correlation_id).strip("-")
    if not safe_correlation:
        raise BenchmarkCaseBuildError.unsafe_correlation_id()
    root = (
        output_root
        / outcome.operational_date.isoformat()
        / "benchbuilder"
        / safe_correlation
    )
    root.mkdir(parents=True, exist_ok=False)
    case_path = root / "case.yaml"
    expected_path = root / "expected_behavior.yaml"
    manifest_path = root / "manifest.json"
    case_id = f"prod-support-benchmark-{outcome.operational_date.isoformat()}"
    _write_yaml(
        case_path,
        {
            "schema_version": 1,
            "status": "captured",
            "review_required": True,
            "id": case_id,
            "prompt": prompt,
            "operational_date": outcome.operational_date.isoformat(),
            "operational_window": {
                "start": outcome.failed_since.isoformat(),
            },
            "regions": [region.value for region in outcome.regions],
            "captured_stages": list(CAPTURED_STAGES),
            "prohibit_raw_logs": True,
        },
    )
    _write_yaml(
        expected_path,
        {
            "schema_version": 1,
            "status": "candidate_expectation",
            "requires_independent_review": True,
            "failure_ids": [failure.failure_id for failure in outcome.failures],
            "diagnoses": [
                {
                    "failure_id": diagnosis.failure_id,
                    "kind": diagnosis.kind.value,
                    "confidence": diagnosis.confidence,
                    "source": diagnosis.source.value,
                    "status": diagnosis.status.value,
                }
                for diagnosis in outcome.diagnoses
            ],
            "report": {
                "full": outcome.report,
                "developer": outcome.developer_report,
                "data_internal": outcome.data_internal_report,
                "follow_up": outcome.follow_up,
            },
            "retry_candidates": [
                {
                    "identity": candidate.identity,
                    "label": candidate.label,
                }
                for candidate in outcome.retry_candidates
            ],
        },
    )
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "captured_at": observed_at.astimezone(UTC).isoformat(),
                "correlation_id": correlation_id,
                "raw_logs_retained": 0,
                "max_parallel": BENCH_BUILDER_MAX_PARALLEL,
                "artifacts": [case_path.name, expected_path.name],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return BenchmarkCaseArtifacts(root, case_path, expected_path, manifest_path)


def _write_yaml(path: Path, value: dict[str, object]) -> None:
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
