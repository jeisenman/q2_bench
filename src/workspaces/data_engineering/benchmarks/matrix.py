"""Manifest models and prompts for benchmark model matrices."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from workspaces.data_engineering.benchmarks.agent_configurations import (
    AgentConfigurationManifestError,
    load_agent_configurations,
)
from workspaces.data_engineering.benchmarks.matrix_prompts import (
    build_capability_prompt_lines,
    build_prod_support_prompt_lines,
)

MAX_SUBAGENT_PARALLELISM = 5


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
    role: str = "candidate"
    capabilities: tuple[str, ...] = ()
    workers: tuple[WorkerProfile, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkerProfile:
    """One subagent worker configuration controlled by a candidate."""

    profile: str
    model: str
    reasoning_effort: str
    capabilities: tuple[str, ...]
    max_parallel: int


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
    candidate_inputs: tuple[Path, ...]
    airflow_base_urls: tuple[tuple[str, str], ...]
    operational_start: str
    operational_end: str
    case_id: str
    capability: str | None
    case_prompt: str
    case_instructions: tuple[str, ...]
    runtime: str
    container_image: str
    parallelism: int
    sandbox: str
    artifact_root: Path
    judge: ModelProfile
    candidates: tuple[ModelProfile, ...]
    rubric: tuple[RubricCriterion, ...]


def load_matrix_run(
    benchmark_path: Path,
    agent_configurations_path: Path,
    cases_path: Path,
    case_id: str,
    configuration_ids: tuple[str, ...] = (),
) -> MatrixManifest:
    """Compose one matrix run from benchmark, agent, and case definitions."""
    raw = yaml.safe_load(benchmark_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise MatrixManifestError.invalid(
            benchmark_path,
            "schema_version must be 1",
        )
    execution = _mapping(raw, "execution", benchmark_path)
    rubric = raw.get("rubric")
    if not isinstance(rubric, list) or not rubric:
        raise MatrixManifestError.invalid(
            benchmark_path,
            "rubric must be a non-empty list",
        )
    try:
        registry = load_agent_configurations(agent_configurations_path)
        selected_raw = (
            tuple(registry.select(profile) for profile in configuration_ids)
            if configuration_ids
            else registry.candidates()
        )
    except AgentConfigurationManifestError as error:
        raise MatrixManifestError(str(error)) from error
    selected = tuple(
        parse_model_profile(profile, agent_configurations_path)
        for profile in selected_raw
    )
    if not selected:
        raise MatrixManifestError.invalid(
            agent_configurations_path,
            "at least one candidate configuration is required",
        )
    case = _load_case(cases_path, case_id)
    operational_window = _mapping(case, "operational_window", cases_path)
    capability = _optional_text(raw, "capability", benchmark_path)
    case_prompt = _optional_text(case, "prompt", cases_path) or ""
    if capability is not None and not case_prompt:
        raise MatrixManifestError.invalid(
            cases_path,
            "capability cases must define a prompt",
        )
    try:
        judge_raw = registry.select(_text(raw, "judge_configuration", benchmark_path))
    except AgentConfigurationManifestError as error:
        raise MatrixManifestError(str(error)) from error
    judge = parse_model_profile(judge_raw, agent_configurations_path)
    if judge.role != "judge":
        raise MatrixManifestError.invalid(
            agent_configurations_path,
            "judge_configuration must reference a judge profile",
        )
    return MatrixManifest(
        matrix_id=_text(raw, "matrix_id", benchmark_path),
        suite=_text(raw, "suite", benchmark_path),
        benchmark=_text(raw, "benchmark", benchmark_path),
        experiment_name=_text(raw, "experiment_name", benchmark_path),
        dataset=Path(_text(case, "dataset_uri", cases_path)),
        candidate_inputs=_path_tuple(case.get("candidate_inputs", []), cases_path),
        airflow_base_urls=_string_pairs(
            case.get("airflow_base_urls", {}),
            cases_path,
        ),
        operational_start=_text(operational_window, "start", cases_path),
        operational_end=_text(operational_window, "end", cases_path),
        case_id=case_id,
        capability=capability,
        case_prompt=case_prompt,
        case_instructions=_string_tuple(case.get("instructions", []), cases_path),
        runtime=str(execution.get("runtime", "process")),
        container_image=str(execution.get("container_image", "")),
        parallelism=int(execution.get("parallelism", len(selected))),
        sandbox=str(execution.get("sandbox", "read-only")),
        artifact_root=Path(str(execution.get("artifact_root", "var/benchmark_matrix"))),
        judge=judge,
        candidates=selected,
        rubric=tuple(_criterion(item, benchmark_path) for item in rubric),
    )


def build_candidate_prompt(
    manifest: MatrixManifest,
    profile: ModelProfile | None = None,
) -> str:
    """Build candidate instructions, including controller-worker roles."""
    selected = profile or manifest.candidates[0]
    lines = (
        build_capability_prompt_lines(manifest, selected)
        if manifest.capability is not None
        else build_prod_support_prompt_lines(manifest, selected)
    )
    if selected.workers:
        lines.append(
            "These configured subagents are available; use them only when they "
            "help the named capability and preserve role attribution in the trace:"
            if manifest.capability is not None
            else "Delegate independent work to these configured subagents and "
            "preserve their role attribution in the trace:"
        )
        lines.extend(
            f"- {worker.profile}: model={worker.model}, "
            f"reasoning={worker.reasoning_effort}, "
            f"max_parallel={worker.max_parallel}, "
            f"capabilities={','.join(worker.capabilities)}"
            for worker in selected.workers
        )
    return "\n".join(lines)


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
    benchmark_kind = (
        f"isolated {manifest.capability} capability"
        if manifest.capability is not None
        else "prod-support"
    )
    return "\n".join(
        (
            f"Judge this {benchmark_kind} agent trace using the weighted rubric.",
            "Score each criterion from 0 to 1. Do not excuse deterministic violations.",
            "Return JSON with overall_score, criteria, strengths, violations, "
            "rationale, and capability_scores. Attribute capability scores to "
            "the controller and worker models declared in the trace.",
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


def _optional_text(raw: dict[str, Any], field: str, path: Path) -> str | None:
    value = raw.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise MatrixManifestError.invalid(
            path,
            f"{field} must be a non-empty string",
        )
    return value


def parse_model_profile(raw: object, path: Path) -> ModelProfile:
    """Parse one reusable model profile."""
    if not isinstance(raw, dict):
        raise MatrixManifestError.invalid(path, "model profile must be a mapping")
    return ModelProfile(
        profile=_text(raw, "profile", path),
        model=_text(raw, "model", path),
        reasoning_effort=_text(raw, "reasoning_effort", path),
        role=str(raw.get("role", "candidate")),
        capabilities=_string_tuple(raw.get("capabilities", []), path),
        workers=tuple(_worker(item, path) for item in raw.get("workers", [])),
    )


def _worker(raw: object, path: Path) -> WorkerProfile:
    if not isinstance(raw, dict):
        raise MatrixManifestError.invalid(path, "worker profile must be a mapping")
    max_parallel = int(raw.get("max_parallel", 1))
    if max_parallel <= 0:
        raise MatrixManifestError.invalid(path, "worker max_parallel must be positive")
    if max_parallel > MAX_SUBAGENT_PARALLELISM:
        raise MatrixManifestError.invalid(
            path,
            f"worker max_parallel must not exceed {MAX_SUBAGENT_PARALLELISM}",
        )
    return WorkerProfile(
        profile=_text(raw, "profile", path),
        model=_text(raw, "model", path),
        reasoning_effort=_text(raw, "reasoning_effort", path),
        capabilities=_string_tuple(raw.get("capabilities", []), path),
        max_parallel=max_parallel,
    )


def _string_tuple(raw: object, path: Path) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(
        isinstance(item, str) and item.strip() for item in raw
    ):
        raise MatrixManifestError.invalid(path, "capabilities must be a string list")
    return tuple(raw)


def _path_tuple(raw: object, path: Path) -> tuple[Path, ...]:
    return tuple(Path(item) for item in _string_tuple(raw, path))


def _string_pairs(raw: object, path: Path) -> tuple[tuple[str, str], ...]:
    if not isinstance(raw, dict) or not all(
        isinstance(key, str)
        and key.strip()
        and isinstance(value, str)
        and value.strip()
        for key, value in raw.items()
    ):
        raise MatrixManifestError.invalid(
            path,
            "airflow_base_urls must be a string mapping",
        )
    return tuple((key, value) for key, value in raw.items())


def _load_case(path: Path, case_id: str) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise MatrixManifestError.invalid(path, "schema_version must be 1")
    cases = raw.get("cases")
    if not isinstance(cases, list):
        raise MatrixManifestError.invalid(path, "cases must be a list")
    for case in cases:
        if isinstance(case, dict) and case.get("id") == case_id:
            return case
    raise MatrixManifestError.invalid(path, f"unknown case: {case_id}")


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
