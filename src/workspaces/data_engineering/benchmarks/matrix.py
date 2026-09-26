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
    case_id: str
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
        case_id=case_id,
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
    lines = [
        "Run the prod-support benchmark using only local recorded evidence.",
        f"Case: {manifest.case_id}",
        f"Dataset: {manifest.dataset}",
        "Additional recorded inputs: "
        f"{', '.join(map(str, manifest.candidate_inputs)) or 'none'}",
        "Airflow base URLs: "
        + ", ".join(f"{region}={url}" for region, url in manifest.airflow_base_urls),
        f"Your role: {selected.role}.",
        f"Your measured capabilities: {', '.join(selected.capabilities) or 'all'}.",
        "Use read-only automation and inspect exact Airflow task logs.",
        "Investigate every failure, including jobs omitted from audience-facing "
        "messages. Do not partition workers into arbitrary record ranges; assign "
        "independent operational capabilities and run independent evidence queries "
        "concurrently.",
        "Required operational workflow:",
        "1. If the latest task log is unavailable or non-diagnostic, page backward "
        "through prior runs of the same DAG and task and cite the first terminal "
        "evidence. Never change task identity.",
        "2. Provide US and CA Airflow failure links bounded by both the lower and "
        "upper end-date limits for the operational day.",
        "3. For each Spark workload, start exact Airflow-log and OMS queries "
        "concurrently. If Airflow proves AirflowTaskTimeout, cancel pending OMS "
        "work and classify the timeout without waiting.",
        "4. Check KEDA ScaledObjects and pod health in both regions. Include explicit "
        "US Cluster Health and CA Cluster Health lines, or identify the exact "
        "missing evidence. Treat access-denied results and capture timestamps as "
        "evidence, never as proof of historical health.",
        "5. Resolve every resend client through the recorded resource-discovery "
        "input. Application selection is hard-gated on an explicit reviewed "
        "production mapping. If none exists, report routing unresolved and do not "
        "substitute a log directive, client subdomain, or guessed application.",
        "6. When a resend exceeds 100 unique events, call it out in both the "
        "Developer and Data Internal messages.",
        "7. Investigate all failures, but omit configured maintenance and subscriber "
        "jobs from the Data Internal message.",
        "8. Group the Developer report naturally by job and provide an evidence-backed "
        "root cause or a precise evidence gap for every reported failure. Use client "
        "names or short aliases in audience messages; keep raw UUIDs, Spark IDs, and "
        "record references out of the Developer and Data Internal messages.",
        "Before returning, audit the final report against all eight workflow items. "
        "Do not claim a check was performed without trace evidence.",
        "Do not mutate production systems. Return the final report only.",
    ]
    if selected.workers:
        lines.append(
            "Delegate independent work to these configured subagents and preserve "
            "their role attribution in the trace:"
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
    return "\n".join(
        (
            "Judge this prod-support agent trace using the weighted rubric.",
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
