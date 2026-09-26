"""Generic inbound adapter for executing manifest-driven benchmark matrices."""

from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any

from adapters.inbound.matrix_results import write_comparison
from adapters.inbound.matrix_runtime import (
    SAFE_PROFILE,
    MatrixRunError,
    _candidate_workspace,
    _codex_auth_source,
    _codex_command,
    _CommandOptions,
)
from workspaces.data_engineering.benchmarks.matrix import (
    MatrixManifest,
    ModelProfile,
    build_candidate_prompt,
    build_matrix_judge_prompt,
)

COMMAND_TIMEOUT_SECONDS = 1800
TRACE_PROMPT_LIMIT = 50_000


@dataclass(frozen=True, slots=True)
class CandidateRun:
    """Locally persisted candidate execution metadata."""

    profile: str
    model: str
    reasoning_effort: str
    elapsed_seconds: float
    final_message: str
    trace_path: Path
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class JudgedRun:
    """Candidate result paired with its LLM-as-a-Judge assessment."""

    candidate: CandidateRun
    overall_score: float
    assessment: dict[str, object]
    assessment_path: Path


@dataclass(frozen=True, slots=True)
class _ExecutionContext:
    workspace: Path
    root: Path
    auth_source: Path


class MatrixInboundAdapter:
    """Execute any benchmark matrix described by the shared manifest contract."""

    def __init__(self, workspace: Path) -> None:
        """Initialize the adapter at the benchmark execution workspace."""
        self._workspace = workspace

    def plan(self, manifest: MatrixManifest) -> tuple[dict[str, object], ...]:
        """Return the candidate plan without invoking any models."""
        return tuple(
            {
                "matrix_id": manifest.matrix_id,
                "profile": item.profile,
                "model": item.model,
                "reasoning_effort": item.reasoning_effort,
                "judge_profile": manifest.judge.profile,
                "runtime": manifest.runtime,
                "role": item.role,
                "capabilities": item.capabilities,
                "workers": tuple(worker.profile for worker in item.workers),
            }
            for item in manifest.candidates
        )

    def run(self, manifest: MatrixManifest) -> tuple[JudgedRun, ...]:
        """Run candidates concurrently, judge them, and persist comparisons."""
        root = manifest.artifact_root
        if root.is_symlink():
            message = f"matrix artifact root may not be a symlink: {root}"
            raise MatrixRunError(message)
        root.mkdir(parents=True, exist_ok=True)
        baselines = _load_baselines(root / "comparison.json")
        with (
            _candidate_workspace(self._workspace, manifest.dataset) as runtime,
            _codex_auth_source() as auth_source,
        ):
            context = _ExecutionContext(runtime, root, auth_source)
            with ThreadPoolExecutor(max_workers=manifest.parallelism) as executor:
                candidates = tuple(
                    executor.map(
                        lambda profile: _run_candidate(
                            manifest,
                            profile,
                            context,
                        ),
                        manifest.candidates,
                    )
                )
            judged = tuple(
                _judge_candidate(
                    manifest,
                    candidate,
                    context,
                    baseline=baselines.get(candidate.profile),
                )
                for candidate in candidates
            )
        write_comparison(manifest, judged, root / "comparison.json")
        return judged


def _run_candidate(
    manifest: MatrixManifest,
    profile: ModelProfile,
    context: _ExecutionContext,
) -> CandidateRun:
    if SAFE_PROFILE.fullmatch(profile.profile) is None:
        message = f"unsafe matrix profile name: {profile.profile}"
        raise MatrixRunError(message)
    profile_root = context.root / profile.profile
    if profile_root.is_symlink():
        message = f"matrix profile output may not be a symlink: {profile_root}"
        raise MatrixRunError(message)
    profile_root.mkdir(parents=True, exist_ok=True)
    final_path = profile_root / "final.md"
    trace_path = profile_root / "trace.jsonl"
    command = _codex_command(
        profile,
        _CommandOptions(
            workspace=context.workspace,
            sandbox=manifest.sandbox,
            final_path=final_path,
            json_output=True,
            runtime=manifest.runtime,
            container_image=manifest.container_image,
            output_root=profile_root,
            auth_source=context.auth_source,
        ),
    )
    started = monotonic()
    process = subprocess.run(
        [*command, build_candidate_prompt(manifest, profile)],
        check=False,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    elapsed = monotonic() - started
    trace_path.write_text(process.stdout, encoding="utf-8")
    (profile_root / "stderr.log").write_text(process.stderr, encoding="utf-8")
    if process.returncode != 0:
        raise MatrixRunError.process_failed(profile.profile, process.returncode)
    events = _json_lines(process.stdout)
    input_tokens, output_tokens = _token_usage(events)
    return CandidateRun(
        profile=profile.profile,
        model=profile.model,
        reasoning_effort=profile.reasoning_effort,
        elapsed_seconds=elapsed,
        final_message=final_path.read_text(encoding="utf-8"),
        trace_path=trace_path,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _judge_candidate(
    manifest: MatrixManifest,
    candidate: CandidateRun,
    context: _ExecutionContext,
    *,
    baseline: dict[str, object] | None,
) -> JudgedRun:
    profile_root = context.root / candidate.profile
    schema_path = profile_root / "judge-schema.json"
    schema_path.write_text(json.dumps(_judge_schema(), indent=2), encoding="utf-8")
    assessment_path = profile_root / "judge.json"
    trace = {
        "profile": candidate.profile,
        "model": candidate.model,
        "reasoning_effort": candidate.reasoning_effort,
        "elapsed_seconds": candidate.elapsed_seconds,
        "input_tokens": candidate.input_tokens,
        "output_tokens": candidate.output_tokens,
        "final_message": candidate.final_message,
        "events": candidate.trace_path.read_text(encoding="utf-8")[:TRACE_PROMPT_LIMIT],
    }
    command = _codex_command(
        manifest.judge,
        _CommandOptions(
            workspace=context.workspace,
            sandbox="read-only",
            final_path=assessment_path,
            json_output=False,
            schema_path=schema_path,
            runtime=manifest.runtime,
            container_image=manifest.container_image,
            output_root=profile_root,
            auth_source=context.auth_source,
        ),
    )
    process = subprocess.run(
        [*command, build_matrix_judge_prompt(manifest, trace, baseline=baseline)],
        check=False,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    if process.returncode != 0:
        raise MatrixRunError.judge_failed(candidate.profile, process.returncode)
    assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
    if not isinstance(assessment, dict):
        raise MatrixRunError.invalid_judgment(candidate.profile)
    return JudgedRun(
        candidate=candidate,
        overall_score=float(assessment["overall_score"]),
        assessment=assessment,
        assessment_path=assessment_path,
    )


def _json_lines(value: str) -> tuple[dict[str, Any], ...]:
    parsed = []
    for line in value.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            parsed.append(item)
    return tuple(parsed)


def _token_usage(events: tuple[dict[str, Any], ...]) -> tuple[int, int]:
    input_tokens = 0
    output_tokens = 0
    for event in events:
        usage = event.get("usage")
        if isinstance(usage, dict):
            input_tokens += int(
                usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0
            )
            output_tokens += int(
                usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0
            )
    return input_tokens, output_tokens


def _judge_schema() -> dict[str, object]:
    criterion = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "score": {"type": "number", "minimum": 0, "maximum": 1},
            "rationale": {"type": "string"},
        },
        "required": ["id", "score", "rationale"],
        "additionalProperties": False,
    }
    capability = {
        "type": "object",
        "properties": {
            "role": {"type": "string"},
            "model": {"type": "string"},
            "capability": {"type": "string"},
            "score": {"type": "number", "minimum": 0, "maximum": 1},
            "rationale": {"type": "string"},
        },
        "required": ["role", "model", "capability", "score", "rationale"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "overall_score": {"type": "number", "minimum": 0, "maximum": 1},
            "criteria": {"type": "array", "items": criterion},
            "capability_scores": {"type": "array", "items": capability},
            "strengths": {"type": "array", "items": {"type": "string"}},
            "violations": {"type": "array", "items": {"type": "string"}},
            "rationale": {"type": "string"},
            "judged_at": {"type": "string"},
        },
        "required": [
            "overall_score",
            "criteria",
            "capability_scores",
            "strengths",
            "violations",
            "rationale",
        ],
        "additionalProperties": False,
    }


def _load_baselines(path: Path) -> dict[str, dict[str, object]]:
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("results"), list):
        return {}
    return {
        str(item["profile"]): item
        for item in raw["results"]
        if isinstance(item, dict) and "profile" in item
    }
