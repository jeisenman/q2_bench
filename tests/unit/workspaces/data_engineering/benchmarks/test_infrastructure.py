from workspaces.data_engineering.benchmarks import (
    DagProcessorObservation,
    assess_dag_processor,
)


def _observation(name: str) -> DagProcessorObservation:
    if name == "pre_bounce":
        return DagProcessorObservation(
            expected_l3_main_count=6,
            observed_l3_main_count=4,
            logs_available=False,
            restart_count=3,
            healthy=False,
        )
    return DagProcessorObservation(
        expected_l3_main_count=6,
        observed_l3_main_count=6,
        logs_available=True,
        restart_count=0,
        healthy=True,
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
