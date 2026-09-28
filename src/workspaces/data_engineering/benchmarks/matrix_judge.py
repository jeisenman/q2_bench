"""Build judge prompts for benchmark matrix traces."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from workspaces.data_engineering.benchmarks.handoff_contracts import (
    handoff_contract_mapping,
)

if TYPE_CHECKING:
    from workspaces.data_engineering.benchmarks.matrix import MatrixManifest


def build_matrix_judge_prompt(
    manifest: MatrixManifest,
    trace: dict[str, object],
    *,
    baseline: dict[str, object] | None = None,
) -> str:
    """Build a weighted judge prompt from one normalized candidate trace."""
    criteria = [
        {
            "id": item.criterion_id,
            "weight": item.weight,
            "reward": item.reward,
            "punish": item.punish,
        }
        for item in manifest.rubric
    ]
    benchmark_kind = (
        f"isolated {manifest.capability} capability"
        if manifest.capability is not None
        else "prod-support"
    )
    handoff_contract = json.dumps(
        handoff_contract_mapping(manifest.handoff_contract),
        sort_keys=True,
    )
    return "\n".join(
        (
            f"Judge this {benchmark_kind} agent trace using the weighted rubric.",
            "Score each criterion from 0 to 1. Do not excuse deterministic violations.",
            "Apply the complete case applicability map before scoring. Criteria "
            "marked false are excluded from the runner's weighted overall score. "
            "Do not use an inapplicable criterion to reward or punish the agent. "
            "When handoff_ordering is false, do not enforce relative call ordering.",
            "For token efficiency, distinguish fresh input from cached input. Score "
            "trace size, uncached input, redundant commands, repeated inventories, "
            "and oversized worker payloads.",
            "Return JSON with overall_score, criteria, strengths, violations, "
            "rationale, capability_scores, and handoff_scores. Attribute every "
            "handoff score to the named agent in the declared contract.",
            "Case applicability: "
            f"{json.dumps(dict(manifest.applicability), sort_keys=True)}",
            f"Expected handoff contract: {handoff_contract}",
            f"Rubric: {json.dumps(criteria, sort_keys=True)}",
            f"Trace: {json.dumps(trace, sort_keys=True)}",
            f"Earlier comparable trace: {json.dumps(baseline or {}, sort_keys=True)}",
        )
    )
