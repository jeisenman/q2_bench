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
    expected_diagnoses:
      US-01|dag|run|task: confirmed_oom
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
                "report": "Message for Data Internal Channel\nPROD SUPPORT\nUS\nCA",
            }
        ),
        encoding="utf-8",
    )

    evaluation = load_recorded_evaluation(cases, "today", result)

    assert evaluation.inputs["case_id"] == "today"
    assert evaluation.outputs["failure_ids"] == ["US-01|dag|run|task"]
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
            "diagnoses": {"failure": "confirmed_oom"},
            "report": "Message for Data Internal Channel\nPROD SUPPORT\nUS\nCA",
        },
        expectations={
            "failed_since": "2026-09-24T05:00:00Z",
            "failure_ids": ["failure"],
            "diagnoses": {"failure": "confirmed_oom"},
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
        "response_formatting",
    ]
