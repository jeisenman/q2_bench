"""Manifest models and prompts for benchmark model matrices."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class MatrixManifestError(ValueError):
    """Raised when a benchmark matrix manifest is invalid."""

    @classmethod
    def invalid(cls, path: Path, reason: str) -> MatrixManifestError:
        """Create an error identifying the invalid manifest."""
        return cls(f"{path}: {reason}")


@dataclass(frozen=True, slots=True)
class ModelProfile:
    """One candidate or judge model configuration."""

    profile: str
    model: str
    reasoning_effort: str


@dataclass(frozen=True, slots=True)
class RubricCriterion:
    """One weighted LLM-as-a-Judge criterion."""

    criterion_id: str
    weight: float
    reward: str
    punish: str


@dataclass(frozen=True, slots=True)
class MatrixManifest:
    """Validated benchmark matrix configuration."""

    matrix_id: str
    suite: str
    benchmark: str
    experiment_name: str
    dataset: Path
    case_id: str
    runtime: str
    container_image: str
    parallelism: int
    sandbox: str
    artifact_root: Path
    judge: ModelProfile
    candidates: tuple[ModelProfile, ...]
    rubric: tuple[RubricCriterion, ...]


def load_matrix_manifest(path: Path) -> MatrixManifest:
    """Load and validate one matrix manifest."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise MatrixManifestError.invalid(path, "schema_version must be 1")
    execution = _mapping(raw, "execution", path)
    candidates = raw.get("candidates")
    rubric = raw.get("rubric")
    if not isinstance(candidates, list) or not candidates:
        raise MatrixManifestError.invalid(
            path,
            "candidates must be a non-empty list",
        )
    if not isinstance(rubric, list) or not rubric:
        raise MatrixManifestError.invalid(path, "rubric must be a non-empty list")
    profiles = tuple(_profile(item, path) for item in candidates)
    if len({item.profile for item in profiles}) != len(profiles):
        raise MatrixManifestError.invalid(path, "candidate profiles must be unique")
    return MatrixManifest(
        matrix_id=_text(raw, "matrix_id", path),
        suite=_text(raw, "suite", path),
        benchmark=_text(raw, "benchmark", path),
        experiment_name=_text(raw, "experiment_name", path),
        dataset=Path(_text(raw, "dataset", path)),
        case_id=_text(raw, "case_id", path),
        runtime=str(execution.get("runtime", "process")),
        container_image=str(execution.get("container_image", "")),
        parallelism=int(execution.get("parallelism", 1)),
        sandbox=str(execution.get("sandbox", "read-only")),
        artifact_root=Path(str(execution.get("artifact_root", "var/benchmark_matrix"))),
        judge=_profile(_mapping(raw, "judge", path), path),
        candidates=profiles,
        rubric=tuple(_criterion(item, path) for item in rubric),
    )


def build_candidate_prompt(manifest: MatrixManifest) -> str:
    """Build the common candidate instruction for a matrix run."""
    return "\n".join(
        (
            "Run the prod-support benchmark using only local recorded evidence.",
            f"Case: {manifest.case_id}",
            f"Dataset: {manifest.dataset}",
            "Use read-only automation and inspect exact Airflow task logs.",
            "Do not mutate production systems. Return the final report only.",
        )
    )


def build_matrix_judge_prompt(
    manifest: MatrixManifest,
    trace: dict[str, object],
    *,
    baseline: dict[str, object] | None = None,
) -> str:
    """Build a weighted judge prompt from one normalized candidate trace."""
    criteria = [
        {
            "id": item.criterion_id,
            "weight": item.weight,
            "reward": item.reward,
            "punish": item.punish,
        }
        for item in manifest.rubric
    ]
    return "\n".join(
        (
            "Judge this prod-support agent trace using the weighted rubric.",
            "Score each criterion from 0 to 1. Do not excuse deterministic violations.",
            "Return JSON with overall_score, criteria, strengths, violations, "
            "and rationale.",
            f"Rubric: {json.dumps(criteria, sort_keys=True)}",
            f"Trace: {json.dumps(trace, sort_keys=True)}",
            f"Earlier comparable trace: {json.dumps(baseline or {}, sort_keys=True)}",
        )
    )


def _mapping(raw: dict[str, Any], field: str, path: Path) -> dict[str, Any]:
    value = raw.get(field)
    if not isinstance(value, dict):
        raise MatrixManifestError.invalid(path, f"{field} must be a mapping")
    return value


def _text(raw: dict[str, Any], field: str, path: Path) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise MatrixManifestError.invalid(
            path,
            f"{field} must be a non-empty string",
        )
    return value


def _profile(raw: object, path: Path) -> ModelProfile:
    if not isinstance(raw, dict):
        raise MatrixManifestError.invalid(path, "model profile must be a mapping")
    return ModelProfile(
        profile=_text(raw, "profile", path),
        model=_text(raw, "model", path),
        reasoning_effort=_text(raw, "reasoning_effort", path),
    )


def _criterion(raw: object, path: Path) -> RubricCriterion:
    if not isinstance(raw, dict):
        raise MatrixManifestError.invalid(path, "rubric criterion must be a mapping")
    weight = float(raw.get("weight", 0))
    if weight <= 0:
        raise MatrixManifestError.invalid(path, "rubric weight must be positive")
    return RubricCriterion(
        criterion_id=_text(raw, "id", path),
        weight=weight,
        reward=_text(raw, "reward", path),
        punish=_text(raw, "punish", path),
    )
