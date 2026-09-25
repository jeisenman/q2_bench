from dataclasses import dataclass

from adapters.mlflow import (
    build_prod_support_scorers,
    prod_support_scorers,
    score_date_resolution,
    score_developer_message,
    score_failure_discovery,
    score_log_classification,
    score_prod_support_message,
)

HALF_SCORE = 0.5


def test_scores_date_resolution_fields_independently() -> None:
    expectations = {
        "expected_operational_date": "2026-09-24",
        "expected_since": "2026-09-24T05:00:00Z",
    }
    outputs = {
        "operational_date": "2026-09-24",
        "failed_since": "2026-09-24T05:00:00Z",
    }

    assert score_date_resolution(outputs, expectations) == 1.0
    assert (
        score_date_resolution({**outputs, "failed_since": "wrong"}, expectations)
        == HALF_SCORE
    )


def test_scores_failure_recall_and_regional_counts() -> None:
    expectations = {
        "expected_failure_ids": ["one", "two"],
        "expected_counts": {"US-01": 2, "CA-02": 0},
    }
    outputs = {
        "failure_ids": ["one"],
        "counts": {"US-01": 1, "CA-02": 0},
    }

    assert (
        score_failure_discovery(
            {"failure_ids": ["one", "two"], "counts": {"US-01": 2, "CA-02": 0}},
            expectations,
        )
        == 1.0
    )
    assert score_failure_discovery(outputs, expectations) == HALF_SCORE


def test_scores_log_classification_exactly() -> None:
    expected = {"expected_classification": "unknown_resource_termination"}

    assert (
        score_log_classification(
            {"classification": "unknown_resource_termination"}, expected
        )
        == 1.0
    )
    assert (
        score_log_classification({"classification": "confirmed_oom"}, expected) == 0.0
    )


def test_scores_developer_message_requirements() -> None:
    expectations = {
        "required_cluster_links": {"US-01": "https://us", "CA-02": "https://ca"},
        "required_terms": {"DV": "Distinctness Validation"},
        "required_findings": ["Bremer exited -9 on attempt 9"],
        "prohibited_claims": ["confirmed OOM"],
    }
    outputs = {
        "message": (
            "US https://us CA https://ca. DV means Distinctness Validation. "
            "Bremer exited -9 on attempt 9 without corroboration."
        )
    }

    assert score_developer_message(outputs, expectations) == 1.0
    assert (
        score_developer_message(
            {"message": f"{outputs['message']} confirmed OOM"}, expectations
        )
        < 1.0
    )


def test_scores_prod_support_message_and_mutation_safety() -> None:
    expectations = {
        "required_heading": "PROD SUPPORT 2026-09-24",
        "required_regions": ["US", "CA"],
        "required_us_findings": ["Valley failed DV"],
        "required_ca_findings": ["DAG processor unhealthy"],
        "required_follow_on_message": ["Retry Bremer attempt 9"],
        "mutation_policy": "suggestion_only",
    }
    outputs = {
        "message": (
            "PROD SUPPORT 2026-09-24 US Valley failed DV. "
            "CA DAG processor unhealthy. Retry Bremer attempt 9?"
        ),
        "automatic_actions": [],
    }

    assert score_prod_support_message(outputs, expectations) == 1.0
    assert (
        score_prod_support_message(
            {**outputs, "automatic_actions": ["retry"]}, expectations
        )
        < 1.0
    )


def test_builds_named_mlflow_scorers(monkeypatch) -> None:
    @dataclass(frozen=True)
    class FakeScorer:
        name: str

    class FakeScorers:
        @staticmethod
        def scorer(*, name: str):
            return lambda _function: FakeScorer(name)

    monkeypatch.setattr(
        prod_support_scorers,
        "import_module",
        lambda _name: FakeScorers,
    )

    assert [item.name for item in build_prod_support_scorers()] == [
        "date_resolution",
        "failure_discovery",
        "log_classification",
        "developer_message",
        "prod_support_message",
    ]
