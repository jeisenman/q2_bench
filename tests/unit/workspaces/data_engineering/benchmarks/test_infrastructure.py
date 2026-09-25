import json
from pathlib import Path

from workspaces.data_engineering.benchmarks import (
    DagProcessorObservation,
    assess_dag_processor,
)

EVIDENCE = (
    Path(__file__).parents[5]
    / "src/workspaces/data_engineering/benchmarks"
    / "production_support/dates/09-25-26/evidence"
    / "current-ca-dag-processor-recovery.json"
)


def _observation(name: str) -> DagProcessorObservation:
    raw = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    selected = next(item for item in raw["observations"] if item["name"] == name)
    return DagProcessorObservation(
        expected_l3_main_count=selected["l3_main"]["expected_count"],
        observed_l3_main_count=selected["l3_main"]["observed_active_count"],
        logs_available=selected["dag_processor"]["logs_available"],
        restart_count=selected["dag_processor"]["restart_count"],
        healthy=selected["dag_processor"]["healthy"],
    )


def test_pre_bounce_mock_reports_user_and_suggests_operator_action() -> None:
    assessment = assess_dag_processor(_observation("pre_bounce"))

    assert assessment.tripped
    assert not assessment.dags_complete
    assert not assessment.logs_available
    assert assessment.repeated_restarts
    assert "report this to the user" in " ".join(assessment.user_messages)
    assert "operator approval" in assessment.suggestions[0]


def test_post_bounce_mock_confirms_recovery_without_another_bounce() -> None:
    assessment = assess_dag_processor(_observation("post_bounce"))

    assert not assessment.tripped
    assert assessment.dags_complete
    assert assessment.logs_available
    assert not assessment.repeated_restarts
    assert assessment.suggestions == ()
