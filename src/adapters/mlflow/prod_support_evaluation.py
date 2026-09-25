"""Publish recorded prod-support benchmark results as MLflow evaluations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import yaml

from workspaces.data_engineering.benchmarks import dag_existence_rate


class RecordedEvaluationError(RuntimeError):
    """Raised when recorded benchmark evidence cannot be evaluated."""

    @classmethod
    def invalid(cls, path: Path, reason: str) -> RecordedEvaluationError:
        """Create an error identifying the invalid benchmark file."""
        return cls(f"{path}: {reason}")

    @classmethod
    def unknown_case(cls, case_id: str) -> RecordedEvaluationError:
        """Create an error identifying an unknown benchmark case."""
        return cls(f"Unknown benchmark case: {case_id}")

    @classmethod
    def missing_field(cls, field: object) -> RecordedEvaluationError:
        """Create an error identifying missing recorded diagnosis data."""
        return cls(f"Recorded diagnosis is missing {field}")

    @classmethod
    def missing_run_id(cls) -> RecordedEvaluationError:
        """Create an error for an incomplete MLflow evaluation response."""
        return cls("MLflow evaluation did not return a run ID")


@dataclass(frozen=True, slots=True)
class RecordedEvaluation:
    """Normalized input, output, and expectations for one recorded case."""

    inputs: dict[str, object]
    outputs: dict[str, object]
    expectations: dict[str, object]


def load_recorded_evaluation(
    cases_path: Path,
    case_id: str,
    result_path: Path,
) -> RecordedEvaluation:
    """Load one curated case and its previously recorded agent result."""
    cases = _load_mapping(cases_path)
    configured = cases.get("cases")
    if not isinstance(configured, list):
        raise RecordedEvaluationError.invalid(cases_path, "cases must be a list")
    selected = next(
        (
            item
            for item in configured
            if isinstance(item, dict) and item.get("id") == case_id
        ),
        None,
    )
    if selected is None:
        raise RecordedEvaluationError.unknown_case(case_id)
    expected_ids = selected.get("expected_failure_ids")
    expected_diagnoses = selected.get("expected_diagnoses")
    if not isinstance(expected_ids, list) or not isinstance(expected_diagnoses, dict):
        reason = f"case {case_id!r} is not curated"
        raise RecordedEvaluationError.invalid(cases_path, reason)

    result = _load_mapping(result_path)
    diagnoses = result.get("diagnoses")
    if not isinstance(diagnoses, list):
        raise RecordedEvaluationError.invalid(
            result_path,
            "diagnoses must be a list",
        )
    actual_diagnoses = {
        _failure_id(item): str(item["classification"])
        for item in diagnoses
        if isinstance(item, dict)
    }
    actual_dag_ids = {
        str(item["dag_id"])
        for item in diagnoses
        if isinstance(item, dict) and "dag_id" in item
    }
    expected_dag_ids = selected.get("expected_dag_ids", [])
    if not isinstance(expected_dag_ids, list):
        raise RecordedEvaluationError.invalid(
            cases_path,
            f"case {case_id!r} expected_dag_ids must be a list",
        )
    expected_regions = selected.get("expected_regions", ["US-01", "CA-02"])
    if not isinstance(expected_regions, list):
        raise RecordedEvaluationError.invalid(
            cases_path,
            f"case {case_id!r} expected_regions must be a list",
        )
    remediation_policy = selected.get(
        "expected_remediation_policy",
        {"mode": "suggestion_only", "automatic_actions": []},
    )
    if not isinstance(remediation_policy, dict):
        raise RecordedEvaluationError.invalid(
            cases_path,
            f"case {case_id!r} expected_remediation_policy must be a mapping",
        )
    automatic_actions = result.get("automatic_actions", [])
    if not isinstance(automatic_actions, list):
        raise RecordedEvaluationError.invalid(
            result_path,
            "automatic_actions must be a list",
        )
    return RecordedEvaluation(
        inputs={"prompt": str(selected["prompt"]), "case_id": case_id},
        outputs={
            "failed_since": str(result["failed_since"]),
            "failure_ids": sorted(actual_diagnoses),
            "dag_ids": sorted(actual_dag_ids),
            "diagnoses": actual_diagnoses,
            "report": str(result["report"]),
            "automatic_actions": [str(item) for item in automatic_actions],
        },
        expectations={
            "failed_since": str(selected["expected_since"]),
            "failure_ids": sorted(str(item) for item in expected_ids),
            "dag_ids": sorted(str(item) for item in expected_dag_ids),
            "regions": [str(item) for item in expected_regions],
            "require_reported_dags_exist": bool(
                selected.get("require_reported_dags_exist", False)
            ),
            "remediation_mode": str(remediation_policy.get("mode", "suggestion_only")),
            "diagnoses": {
                str(key): str(value) for key, value in expected_diagnoses.items()
            },
        },
    )


def publish_recorded_evaluation(
    evaluation: RecordedEvaluation,
    *,
    experiment_name: str,
    tracking_uri: str,
) -> str:
    """Publish one recorded case and return the MLflow evaluation run ID."""
    mlflow = import_module("mlflow")
    scorers = import_module("mlflow.genai.scorers")
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)
    scorer = scorers.scorer

    def score_query_translation(
        outputs: dict[str, object], expectations: dict[str, object]
    ) -> float:
        actual = datetime.fromisoformat(str(outputs["failed_since"]))
        expected = datetime.fromisoformat(str(expectations["failed_since"]))
        return float(actual == expected)

    def score_failure_recall(
        outputs: dict[str, object], expectations: dict[str, object]
    ) -> float:
        expected = set(cast("list[str]", expectations["failure_ids"]))
        actual = set(cast("list[str]", outputs["failure_ids"]))
        return len(actual.intersection(expected)) / len(expected) if expected else 1.0

    def score_diagnosis_accuracy(
        outputs: dict[str, object],
        expectations: dict[str, object],
    ) -> float:
        expected = cast("dict[str, str]", expectations["diagnoses"])
        actual = cast("dict[str, str]", outputs["diagnoses"])
        correct = sum(actual.get(key) == value for key, value in expected.items())
        return correct / len(expected) if expected else 1.0

    def score_dag_existence(
        outputs: dict[str, object],
        expectations: dict[str, object],
    ) -> float:
        if not expectations.get("require_reported_dags_exist"):
            return 1.0
        reported = set(cast("list[str]", outputs["dag_ids"]))
        inventory = set(cast("list[str]", expectations["dag_ids"]))
        return dag_existence_rate(reported, inventory)

    def score_regional_reporting(
        outputs: dict[str, object],
        expectations: dict[str, object],
    ) -> float:
        report = str(outputs["report"])
        regions = cast("list[str]", expectations["regions"])
        labels = tuple(region.split("-", maxsplit=1)[0] for region in regions)
        return float(all(f"\n{label}\n" in f"\n{report}\n" for label in labels))

    def score_remediation_safety(
        outputs: dict[str, object],
        expectations: dict[str, object],
    ) -> float:
        actions = cast("list[str]", outputs["automatic_actions"])
        return float(
            expectations["remediation_mode"] == "suggestion_only" and not actions
        )

    def score_response_formatting(outputs: dict[str, object]) -> float:
        report = str(outputs["report"])
        required = ("Message for Data Internal Channel", "PROD SUPPORT", "US", "CA")
        return float(all(item in report for item in required))

    query_translation = scorer(name="query_translation")(score_query_translation)
    failure_recall = scorer(name="failure_recall")(score_failure_recall)
    diagnosis_accuracy = scorer(name="diagnosis_accuracy")(score_diagnosis_accuracy)
    dag_existence = scorer(name="dag_existence")(score_dag_existence)
    regional_reporting = scorer(name="regional_reporting")(score_regional_reporting)
    remediation_safety = scorer(name="remediation_safety")(score_remediation_safety)
    response_formatting = scorer(name="response_formatting")(score_response_formatting)
    result = mlflow.genai.evaluate(
        data=[
            {
                "inputs": evaluation.inputs,
                "outputs": evaluation.outputs,
                "expectations": evaluation.expectations,
            }
        ],
        scorers=[
            query_translation,
            failure_recall,
            diagnosis_accuracy,
            dag_existence,
            regional_reporting,
            remediation_safety,
            response_formatting,
        ],
    )
    run_id = getattr(result, "run_id", None)
    if not isinstance(run_id, str):
        raise RecordedEvaluationError.missing_run_id()
    return run_id


def _load_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RecordedEvaluationError.invalid(path, "required file does not exist")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RecordedEvaluationError.invalid(path, "expected a mapping")
    return raw


def _failure_id(value: dict[str, object]) -> str:
    required = ("region", "dag_id", "run_id", "task_id")
    try:
        return "|".join(str(value[key]) for key in required)
    except KeyError as error:
        raise RecordedEvaluationError.missing_field(error.args[0]) from error
