"""Publish grouped benchmark matrix results to MLflow."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Protocol

from adapters.inbound import JudgedRun
from adapters.inbound.matrix_results import capability_scores
from workspaces.data_engineering.benchmarks import MatrixManifest


class _ArtifactLogger(Protocol):
    def log_artifact(self, local_path: str, artifact_path: str) -> None:
        """Log one local artifact."""


def publish_matrix_results(
    manifest: MatrixManifest,
    results: tuple[JudgedRun, ...],
    *,
    tracking_uri: str,
) -> str:
    """Publish one parent matrix run and nested comparable candidate runs."""
    mlflow = import_module("mlflow")
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(manifest.experiment_name)
    tags = {
        "benchmark.matrix_id": manifest.matrix_id,
        "benchmark.suite": manifest.suite,
        "benchmark.case_id": manifest.case_id,
        "benchmark.judge": manifest.judge.profile,
    }
    with mlflow.start_run(run_name=manifest.matrix_id, tags=tags) as parent:
        for result in results:
            candidate = result.candidate
            child_tags = {
                **tags,
                "benchmark.profile": candidate.profile,
                "benchmark.model": candidate.model,
                "benchmark.reasoning_effort": candidate.reasoning_effort,
            }
            with mlflow.start_run(
                run_name=candidate.profile,
                tags=child_tags,
                nested=True,
            ):
                mlflow.log_metrics(
                    {
                        "judge_score": result.overall_score,
                        "elapsed_seconds": candidate.elapsed_seconds,
                        "input_tokens": candidate.input_tokens,
                        "output_tokens": candidate.output_tokens,
                        **_capability_metrics(result.assessment),
                    }
                )
                mlflow.log_dict(result.assessment, "judge/assessment.json")
                _log_if_present(mlflow, candidate.trace_path)
                _log_if_present(mlflow, result.assessment_path)
        return str(parent.info.run_id)


def _log_if_present(mlflow: _ArtifactLogger, path: Path) -> None:
    if path.is_file():
        mlflow.log_artifact(str(path), artifact_path="matrix")


def _capability_metric_name(item: dict[str, object]) -> str:
    role = str(item.get("role", "unknown")).replace("-", "_")
    capability = str(item.get("capability", "unknown")).replace("-", "_")
    return f"capability.{role}.{capability}"


def _capability_metrics(assessment: dict[str, object]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for item in capability_scores(assessment):
        score = item.get("score")
        if isinstance(score, int | float):
            metrics[_capability_metric_name(item)] = float(score)
    return metrics
