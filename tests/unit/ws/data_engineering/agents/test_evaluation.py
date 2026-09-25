from datetime import UTC, date, datetime

from agentsdk.ws.data_engineering.agents.prod_support.evaluation import (
    ProdSupportExpectation,
    evaluate_outcome,
)
from agentsdk.ws.data_engineering.agents.prod_support.models import (
    AirflowFailure,
    FailureDiagnosis,
    FailureKind,
    ProdSupportOutcome,
    Region,
)


def test_evaluate_outcome_scores_each_workflow_stage() -> None:
    cutoff = datetime(2026, 9, 24, 5, tzinfo=UTC)
    failure = AirflowFailure(
        Region.US_01,
        "dag",
        "run",
        "task",
        cutoff,
        datetime(2026, 9, 24, 6, tzinfo=UTC),
    )
    outcome = ProdSupportOutcome(
        date(2026, 9, 24),
        cutoff,
        (failure,),
        (
            FailureDiagnosis(
                failure.failure_id,
                FailureKind.CONFIRMED_OOM,
                "confirmed",
                ("OOMKilled",),
            ),
        ),
        "Message for Data Internal Channel\nPROD SUPPORT 2026-09-24\nUS\nCA",
    )
    expected = ProdSupportExpectation(
        cutoff,
        frozenset({failure.failure_id}),
        ((failure.failure_id, FailureKind.CONFIRMED_OOM),),
    )

    scores = evaluate_outcome(outcome, expected)

    assert scores.query_translation == 1.0
    assert scores.failure_recall == 1.0
    assert scores.diagnosis_accuracy == 1.0
    assert scores.formatting == 1.0
