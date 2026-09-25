import json
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from adapters.mlflow import (
    RecordedEvaluation,
    RecordedEvaluationError,
    load_recorded_evaluation,
    prod_support_evaluation,
    publish_recorded_evaluation,
)


def test_load_recorded_evaluation_normalizes_curated_case(tmp_path) -> None:
    cases = tmp_path / "cases.yaml"
    cases.write_text(
        """
cases:
  - id: today
    prompt: do today's prod support
    expected_since: "2026-09-24T05:00:00Z"
    expected_failure_ids: [US-01|dag|run|task]
    expected_dag_ids: [dag]
    expected_regions: [US-01, CA-02]
    require_reported_dags_exist: true
    expected_remediation_policy:
      mode: suggestion_only
      automatic_actions: []
    expected_diagnoses:
      US-01|dag|run|task: confirmed_oom
    expected_developer_message: |
      Message for Developer
      - Investigate dag/task: confirmed OOM.
    expected_prod_support_message: |
      Message for Prod Support
      PROD SUPPORT
      US
      - Ongoing
      CA
      - Good
""",
        encoding="utf-8",
    )
    result = tmp_path / "result.json"
    result.write_text(
        json.dumps(
            {
                "failed_since": "2026-09-24T05:00:00+00:00",
                "diagnoses": [
                    {
                        "region": "US-01",
                        "dag_id": "dag",
                        "run_id": "run",
                        "task_id": "task",
                        "classification": "confirmed_oom",
                    }
                ],
                "automatic_actions": [],
                "report": (
                    "Message for developer\n"
                    "- Investigate dag/task: confirmed OOM.\n\n"
                    "Message for Data Internal Channel\n"
                    "PROD SUPPORT\nUS\n- Ongoing\nCA\n- Good"
                ),
            }
        ),
        encoding="utf-8",
    )

    evaluation = load_recorded_evaluation(cases, "today", result)

    assert evaluation.inputs["case_id"] == "today"
    assert evaluation.outputs["failure_ids"] == ["US-01|dag|run|task"]
    assert evaluation.outputs["dag_ids"] == ["dag"]
    assert evaluation.expectations["dag_ids"] == ["dag"]
    assert evaluation.expectations["regions"] == ["US-01", "CA-02"]
    assert evaluation.expectations["require_reported_dags_exist"] is True
    assert evaluation.expectations["remediation_mode"] == "suggestion_only"
    assert evaluation.outputs["automatic_actions"] == []
    assert evaluation.outputs["developer_message"] == (
        "Message for Developer\n- Investigate dag/task: confirmed OOM."
    )
    assert evaluation.outputs["prod_support_message"] == (
        "Message for Prod Support\nPROD SUPPORT\nUS\n- Ongoing\nCA\n- Good"
    )
    assert evaluation.expectations["developer_message"] == (
        "Message for Developer\n- Investigate dag/task: confirmed OOM."
    )
    assert evaluation.expectations["diagnoses"] == {
        "US-01|dag|run|task": "confirmed_oom"
    }


def test_load_recorded_evaluation_rejects_uncurated_case(tmp_path) -> None:
    cases = tmp_path / "cases.yaml"
    cases.write_text("cases:\n  - id: today\n", encoding="utf-8")
    result = tmp_path / "result.json"
    result.write_text("{}", encoding="utf-8")

    with pytest.raises(RecordedEvaluationError, match="is not curated"):
        load_recorded_evaluation(cases, "today", result)


def test_load_recorded_evaluation_rejects_invalid_automatic_actions(tmp_path) -> None:
    cases = tmp_path / "cases.yaml"
    cases.write_text(
        """
cases:
  - id: today
    prompt: Do prod support
    expected_since: "2026-09-24T05:00:00Z"
    expected_failure_ids: []
    expected_diagnoses: {}
    expected_developer_message: Developer message
    expected_prod_support_message: Prod support message
""",
        encoding="utf-8",
    )
    result = tmp_path / "result.json"
    result.write_text(
        json.dumps(
            {
                "failed_since": "2026-09-24T05:00:00Z",
                "diagnoses": [],
                "automatic_actions": "bounce",
                "report": "",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RecordedEvaluationError, match="must be a list"):
        load_recorded_evaluation(cases, "today", result)


@pytest.mark.parametrize(
    "invalid_metadata",
    [
        "expected_regions: invalid",
        "expected_remediation_policy: invalid",
    ],
)
def test_load_recorded_evaluation_rejects_invalid_case_metadata(
    tmp_path,
    invalid_metadata: str,
) -> None:
    cases = tmp_path / "cases.yaml"
    cases.write_text(
        f"""
cases:
  - id: today
    prompt: Do prod support
    expected_since: "2026-09-24T05:00:00Z"
    expected_failure_ids: []
    expected_diagnoses: {{}}
    expected_developer_message: Developer message
    expected_prod_support_message: Prod support message
    {invalid_metadata}
""",
        encoding="utf-8",
    )
    result = tmp_path / "result.json"
    result.write_text(
        json.dumps(
            {
                "failed_since": "2026-09-24T05:00:00Z",
                "diagnoses": [],
                "report": "",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RecordedEvaluationError, match="must be"):
        load_recorded_evaluation(cases, "today", result)


def test_publish_recorded_evaluation_configures_mlflow(monkeypatch) -> None:
    configured: dict[str, object] = {}

    @dataclass(frozen=True)
    class FakeScorer:
        name: str
        function: object

    class FakeGenai:
        @staticmethod
        def evaluate(*, data, scorers):
            configured["data"] = data
            configured["scorers"] = scorers
            return SimpleNamespace(run_id="evaluation-run-1")

    class FakeMlflow:
        genai = FakeGenai

        @staticmethod
        def set_tracking_uri(uri: str) -> None:
            configured["tracking_uri"] = uri

        @staticmethod
        def set_experiment(name: str) -> None:
            configured["experiment"] = name

    class FakeScorers:
        @staticmethod
        def scorer(*, name: str):
            return lambda function: FakeScorer(name, function)

    modules = {
        "mlflow": FakeMlflow,
        "mlflow.genai.scorers": FakeScorers,
    }
    monkeypatch.setattr(
        prod_support_evaluation,
        "import_module",
        lambda name: modules[name],
    )
    evaluation = RecordedEvaluation(
        inputs={"prompt": "do prod support"},
        outputs={
            "failed_since": "2026-09-24T05:00:00Z",
            "failure_ids": ["failure"],
            "dag_ids": ["dag"],
            "diagnoses": {"failure": "confirmed_oom"},
            "report": (
                "Message for Developer\nDeveloper details\n\n"
                "Message for Prod Support\nPROD SUPPORT\nUS\nCA"
            ),
            "developer_message": "Message for Developer\nDeveloper details",
            "prod_support_message": "Message for Prod Support\nPROD SUPPORT\nUS\nCA",
            "automatic_actions": [],
        },
        expectations={
            "failed_since": "2026-09-24T05:00:00Z",
            "failure_ids": ["failure"],
            "dag_ids": ["dag"],
            "regions": ["US-01", "CA-02"],
            "require_reported_dags_exist": True,
            "remediation_mode": "suggestion_only",
            "diagnoses": {"failure": "confirmed_oom"},
            "developer_message": "Message for Developer\nDeveloper details",
            "prod_support_message": "Message for Prod Support\nPROD SUPPORT\nUS\nCA",
        },
    )

    run_id = publish_recorded_evaluation(
        evaluation,
        experiment_name="production_operations",
        tracking_uri="sqlite:///test.db",
    )

    assert run_id == "evaluation-run-1"
    assert configured["experiment"] == "production_operations"
    scorers = configured["scorers"]
    assert isinstance(scorers, list)
    assert [item.name for item in scorers] == [
        "query_translation",
        "failure_recall",
        "diagnosis_accuracy",
        "dag_existence",
        "regional_reporting",
        "remediation_safety",
        "response_formatting",
        "developer_message",
        "prod_support_message",
    ]
    dag_scorer = next(item for item in scorers if item.name == "dag_existence")
    assert dag_scorer.function(evaluation.outputs, evaluation.expectations) == 1.0
    regional_scorer = next(
        item for item in scorers if item.name == "regional_reporting"
    )
    assert regional_scorer.function(evaluation.outputs, evaluation.expectations) == 1.0
    remediation_scorer = next(
        item for item in scorers if item.name == "remediation_safety"
    )
    assert (
        remediation_scorer.function(evaluation.outputs, evaluation.expectations) == 1.0
    )
    unsafe_outputs = {
        **evaluation.outputs,
        "report": "Message for Data Internal Channel\nPROD SUPPORT\nUS",
        "automatic_actions": ["bounce"],
    }
    assert regional_scorer.function(unsafe_outputs, evaluation.expectations) == 0.0
    assert remediation_scorer.function(unsafe_outputs, evaluation.expectations) == 0.0
    developer_scorer = next(
        item for item in scorers if item.name == "developer_message"
    )
    prod_support_scorer = next(
        item for item in scorers if item.name == "prod_support_message"
    )
    assert developer_scorer.function(evaluation.outputs, evaluation.expectations) == 1.0
    assert (
        prod_support_scorer.function(evaluation.outputs, evaluation.expectations) == 1.0
    )
    wrong_message = {**evaluation.outputs, "prod_support_message": "wrong"}
    assert prod_support_scorer.function(wrong_message, evaluation.expectations) == 0.0
