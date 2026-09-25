"""Generic inbound adapter for executing manifest-driven benchmark matrices."""

from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from time import monotonic
from typing import Any

from workspaces.data_engineering.benchmarks.matrix import (
    MatrixManifest,
    ModelProfile,
    build_candidate_prompt,
    build_matrix_judge_prompt,
)

COMMAND_TIMEOUT_SECONDS = 1800
TRACE_PROMPT_LIMIT = 50_000


class MatrixRunError(RuntimeError):
    """Raised when a candidate or judge process fails."""

    @classmethod
    def process_failed(cls, name: str, returncode: int) -> MatrixRunError:
        """Create an error for a failed candidate or judge process."""
        return cls(f"{name} failed with exit code {returncode}")

    @classmethod
    def invalid_judgment(cls, profile: str) -> MatrixRunError:
        """Create an error for malformed judge output."""
        return cls(f"judge returned invalid JSON for {profile}")

    @classmethod
    def judge_failed(cls, profile: str, returncode: int) -> MatrixRunError:
        """Create an error for a failed judge process."""
        return cls(f"judge for {profile} failed with exit code {returncode}")

    @classmethod
    def path_outside_workspace(cls, path: Path) -> MatrixRunError:
        """Create an error for a path unavailable to a worker container."""
        return cls(f"container path must be inside workspace: {path}")


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
            }
            for item in manifest.candidates
        )

    def run(self, manifest: MatrixManifest) -> tuple[JudgedRun, ...]:
        """Run candidates concurrently, judge them, and persist comparisons."""
        root = manifest.artifact_root
        root.mkdir(parents=True, exist_ok=True)
        baselines = _load_baselines(root / "comparison.json")
        with ThreadPoolExecutor(max_workers=manifest.parallelism) as executor:
            candidates = tuple(
                executor.map(
                    lambda profile: _run_candidate(
                        manifest,
                        profile,
                        workspace=self._workspace,
                        root=root,
                    ),
                    manifest.candidates,
                )
            )
        judged = tuple(
            _judge_candidate(
                manifest,
                candidate,
                workspace=self._workspace,
                root=root,
                baseline=baselines.get(candidate.profile),
            )
            for candidate in candidates
        )
        _write_comparison(manifest, judged, root / "comparison.json")
        return judged


def _run_candidate(
    manifest: MatrixManifest,
    profile: ModelProfile,
    *,
    workspace: Path,
    root: Path,
) -> CandidateRun:
    profile_root = root / profile.profile
    profile_root.mkdir(parents=True, exist_ok=True)
    final_path = profile_root / "final.md"
    trace_path = profile_root / "trace.jsonl"
    command = _codex_command(
        profile,
        _CommandOptions(
            workspace=workspace,
            sandbox=manifest.sandbox,
            final_path=final_path,
            json_output=True,
            runtime=manifest.runtime,
            container_image=manifest.container_image,
        ),
    )
    started = monotonic()
    process = subprocess.run(
        [*command, build_candidate_prompt(manifest)],
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
    *,
    workspace: Path,
    root: Path,
    baseline: dict[str, object] | None,
) -> JudgedRun:
    profile_root = root / candidate.profile
    schema_path = root / "judge-schema.json"
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
            workspace=workspace,
            sandbox="read-only",
            final_path=assessment_path,
            json_output=False,
            schema_path=schema_path,
            runtime=manifest.runtime,
            container_image=manifest.container_image,
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


@dataclass(frozen=True, slots=True)
class _CommandOptions:
    workspace: Path
    sandbox: str
    final_path: Path
    json_output: bool
    schema_path: Path | None = None
    runtime: str = "process"
    container_image: str = ""


def _codex_command(profile: ModelProfile, options: _CommandOptions) -> list[str]:
    sandbox = (
        "danger-full-access" if options.runtime == "container" else options.sandbox
    )
    command = [
        "--model",
        profile.model,
        "-c",
        f'model_reasoning_effort="{profile.reasoning_effort}"',
        "--sandbox",
        sandbox,
        "--ask-for-approval",
        "never",
        "--cd",
        _runtime_path(options.workspace, options),
        "exec",
        "--ephemeral",
        "--output-last-message",
        _runtime_path(options.final_path, options),
    ]
    if options.json_output:
        command.append("--json")
    if options.schema_path is not None:
        command.extend(("--output-schema", _runtime_path(options.schema_path, options)))
    if options.runtime != "container":
        return ["codex", *command]
    env_file = options.workspace / ".env"
    return [
        "docker",
        "run",
        "--rm",
        *(["--env-file", str(env_file)] if env_file.is_file() else []),
        "--env",
        "SSL_CERT_FILE=/home/agentbench/.aws/q2-ca-bundle.pem",
        "--tmpfs",
        "/home/agentbench/.bedrock_codex:uid=1000,gid=1000,mode=0700",
        "--volume",
        f"{options.workspace}:/workspace:ro",
        "--volume",
        f"{options.workspace / 'var'}:/workspace/var",
        "--volume",
        f"{Path.home() / '.bedrock_codex'}:/mnt/codex-host:ro",
        "--volume",
        f"{Path.home() / '.aws'}:/home/agentbench/.aws:ro",
        "--workdir",
        "/workspace",
        options.container_image,
        "codex",
        *command,
    ]


def _runtime_path(path: Path, options: _CommandOptions) -> str:
    if options.runtime != "container":
        return str(path)
    try:
        relative = path.resolve().relative_to(options.workspace.resolve())
    except ValueError as error:
        raise MatrixRunError.path_outside_workspace(path) from error
    return str(Path("/workspace") / relative)


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
            input_tokens += int(usage.get("input_tokens", 0))
            output_tokens += int(usage.get("output_tokens", 0))
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
    return {
        "type": "object",
        "properties": {
            "overall_score": {"type": "number", "minimum": 0, "maximum": 1},
            "criteria": {"type": "array", "items": criterion},
            "strengths": {"type": "array", "items": {"type": "string"}},
            "violations": {"type": "array", "items": {"type": "string"}},
            "rationale": {"type": "string"},
            "judged_at": {"type": "string"},
        },
        "required": [
            "overall_score",
            "criteria",
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


def _write_comparison(
    manifest: MatrixManifest,
    judged: tuple[JudgedRun, ...],
    path: Path,
) -> None:
    comparison = {
        "matrix_id": manifest.matrix_id,
        "suite": manifest.suite,
        "case_id": manifest.case_id,
        "judge": asdict(manifest.judge),
        "results": [
            {
                "profile": item.candidate.profile,
                "model": item.candidate.model,
                "reasoning_effort": item.candidate.reasoning_effort,
                "score": item.overall_score,
                "elapsed_seconds": item.candidate.elapsed_seconds,
                "input_tokens": item.candidate.input_tokens,
                "output_tokens": item.candidate.output_tokens,
            }
            for item in judged
        ],
    }
    path.write_text(
        json.dumps(comparison, indent=2, sort_keys=True),
        encoding="utf-8",
    )
