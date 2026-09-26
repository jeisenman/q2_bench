"""Persist matrix comparisons with model-role capability measurements."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adapters.inbound.matrix import JudgedRun
    from workspaces.data_engineering.benchmarks import MatrixManifest


def capability_scores(assessment: dict[str, object]) -> list[dict[str, object]]:
    """Return validated role-level capability score records."""
    raw = assessment.get("capability_scores", [])
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def write_comparison(
    manifest: MatrixManifest,
    judged: tuple[JudgedRun, ...],
    path: Path,
) -> None:
    """Write aggregate and per-role capability results."""
    comparison = {
        "matrix_id": manifest.matrix_id,
        "suite": manifest.suite,
        "case_id": manifest.case_id,
        "judge": asdict(manifest.judge),
        "results": [
            {
                "profile": item.candidate.profile,
                "model": item.candidate.model,
                "reasoning_effort": item.candidate.reasoning_effort,
                "score": item.overall_score,
                "elapsed_seconds": item.candidate.elapsed_seconds,
                "input_tokens": item.candidate.input_tokens,
                "output_tokens": item.candidate.output_tokens,
                "capability_scores": capability_scores(item.assessment),
            }
            for item in judged
        ],
    }
    path.write_text(
        json.dumps(comparison, indent=2, sort_keys=True),
        encoding="utf-8",
    )
