"""Evaluate production-support outcomes by workflow stage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from workspaces.data_engineering.workflows.prod_support.models import (
    FailureKind,
    ProdSupportOutcome,
)


@dataclass(frozen=True, slots=True)
class ProdSupportExpectation:
    """Human-curated labels for one benchmark case."""

    expected_since: datetime
    failure_ids: frozenset[str]
    diagnoses: tuple[tuple[str, FailureKind], ...]


@dataclass(frozen=True, slots=True)
class ProdSupportScores:
    """Scores for each independently diagnosable workflow stage."""

    query_translation: float
    failure_recall: float
    diagnosis_accuracy: float
    formatting: float


def evaluate_outcome(
    outcome: ProdSupportOutcome,
    expected: ProdSupportExpectation,
) -> ProdSupportScores:
    """Score query translation, capture, diagnosis, and report formatting."""
    actual_ids = {failure.failure_id for failure in outcome.failures}
    found = len(actual_ids.intersection(expected.failure_ids))
    recall = found / len(expected.failure_ids) if expected.failure_ids else 1.0
    expected_diagnoses = dict(expected.diagnoses)
    actual_diagnoses = {
        diagnosis.failure_id: diagnosis.kind for diagnosis in outcome.diagnoses
    }
    correct = sum(
        actual_diagnoses.get(failure_id) is kind
        for failure_id, kind in expected_diagnoses.items()
    )
    accuracy = correct / len(expected_diagnoses) if expected_diagnoses else 1.0
    required_fragments = (
        "Message for Data Internal Channel",
        f"PROD SUPPORT {outcome.operational_date.isoformat()}",
        "US",
        "CA",
    )
    formatting = float(all(item in outcome.report for item in required_fragments))
    return ProdSupportScores(
        query_translation=float(outcome.failed_since == expected.expected_since),
        failure_recall=recall,
        diagnosis_accuracy=accuracy,
        formatting=formatting,
    )
