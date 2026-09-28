"""Deterministically aggregate only applicable benchmark rubric criteria."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from adapters.inbound.matrix_runtime import MatrixRunError

if TYPE_CHECKING:
    from workspaces.data_engineering.benchmarks.matrix import MatrixManifest


def applicable_weighted_score(
    manifest: MatrixManifest,
    assessment: Mapping[str, object],
) -> float:
    """Return the weighted score after excluding inapplicable criteria."""
    raw_criteria = assessment.get("criteria")
    if not isinstance(raw_criteria, list):
        raise MatrixRunError.missing_score_criteria()
    scores: dict[str, float] = {}
    for item in raw_criteria:
        if not isinstance(item, Mapping):
            raise MatrixRunError.invalid_score_criterion()
        criterion_id = item.get("id")
        score = item.get("score")
        if not isinstance(criterion_id, str) or not isinstance(score, (int, float)):
            raise MatrixRunError.invalid_score_fields()
        if criterion_id in scores:
            raise MatrixRunError.duplicate_score_criterion(criterion_id)
        scores[criterion_id] = float(score)
    applicability = dict(manifest.applicability)
    active = tuple(
        criterion
        for criterion in manifest.rubric
        if applicability[criterion.criterion_id]
    )
    if not active:
        raise MatrixRunError.no_applicable_score_criteria()
    missing = tuple(
        item.criterion_id for item in active if item.criterion_id not in scores
    )
    if missing:
        raise MatrixRunError.omitted_score_criteria(missing)
    weighted = sum(scores[item.criterion_id] * item.weight for item in active)
    return weighted / sum(item.weight for item in active)
