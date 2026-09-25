import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from adapters.inbound import (
    CandidateRun,
    JudgedRun,
    MatrixInboundAdapter,
    MatrixRunError,
    matrix,
)
from workspaces.data_engineering.benchmarks import load_matrix_manifest

MATRIX_PATH = (
    Path(__file__).parents[4]
    / "src/workspaces/data_engineering/benchmarks/production_support"
    / "dates/09-25-26/matrix.yaml"
)
CANDIDATE_COUNT = 6
INPUT_TOKENS = 11
JUDGE_SCORE = 0.75
OUTPUT_TOKENS = 7


def candidate(root: Path, profile: str) -> CandidateRun:
    trace = root / profile / "trace.jsonl"
    trace.parent.mkdir(parents=True, exist_ok=True)
    trace.write_text("{}\n", encoding="utf-8")
    return CandidateRun(
        profile=profile,
        model="model",
        reasoning_effort="low",
        elapsed_seconds=1.5,
        final_message="report",
        trace_path=trace,
        input_tokens=10,
        output_tokens=5,
    )


def judged(root: Path, profile: str) -> JudgedRun:
    assessment = root / profile / "judge.json"
    assessment.write_text('{"overall_score": 0.8}', encoding="utf-8")
    return JudgedRun(
        candidate=candidate(root, profile),
        overall_score=0.8,
        assessment={"overall_score": 0.8},
        assessment_path=assessment,
    )


def test_adapter_runs_profiles_and_reuses_baselines(monkeypatch, tmp_path) -> None:
    manifest = replace(
        load_matrix_manifest(MATRIX_PATH),
        artifact_root=tmp_path,
    )
    observed_baselines: list[dict[str, object] | None] = []
    (tmp_path / "comparison.json").write_text(
        '{"results": [{"profile": "sol-light", "elapsed_seconds": 2}]}',
        encoding="utf-8",
    )

    def fake_candidate(_manifest, profile, *, workspace, root):
        assert workspace == Path.cwd()
        return candidate(root, profile.profile)

    def fake_judge(_manifest, item, *, workspace, root, baseline):
        assert workspace == Path.cwd()
        observed_baselines.append(baseline)
        return judged(root, item.profile)

    monkeypatch.setattr(matrix, "_run_candidate", fake_candidate)
    monkeypatch.setattr(matrix, "_judge_candidate", fake_judge)

    results = MatrixInboundAdapter(Path.cwd()).run(manifest)

    assert len(results) == CANDIDATE_COUNT
    assert observed_baselines[0] == {
        "profile": "sol-light",
        "elapsed_seconds": 2,
    }
    comparison = json.loads((tmp_path / "comparison.json").read_text())
    assert len(comparison["results"]) == CANDIDATE_COUNT


def test_command_builds_container_and_process_variants(tmp_path) -> None:
    workspace = tmp_path.resolve()
    target = workspace / "var" / "final.md"
    profile = load_matrix_manifest(MATRIX_PATH).candidates[0]
    container = matrix._codex_command(
        profile,
        matrix._CommandOptions(
            workspace=workspace,
            sandbox="read-only",
            final_path=target,
            json_output=True,
            runtime="container",
            container_image="image",
        ),
    )
    process = matrix._codex_command(
        profile,
        matrix._CommandOptions(
            workspace=workspace,
            sandbox="read-only",
            final_path=target,
            json_output=False,
        ),
    )

    assert container[:2] == ["docker", "run"]
    assert "/workspace/var/final.md" in container
    assert "--json" in container
    assert process[0] == "codex"


def test_trace_helpers_and_schema(tmp_path) -> None:
    events = matrix._json_lines(
        '{"usage": {"input_tokens": 3, "output_tokens": 2}}\ninvalid\n{}'
    )

    assert matrix._token_usage(events) == (3, 2)
    assert matrix._judge_schema()["type"] == "object"
    assert matrix._load_baselines(tmp_path / "missing.json") == {}
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")
    assert matrix._load_baselines(invalid) == {}


def test_container_path_must_be_inside_workspace(tmp_path) -> None:
    options = matrix._CommandOptions(
        workspace=tmp_path / "workspace",
        sandbox="read-only",
        final_path=tmp_path / "output",
        json_output=False,
        runtime="container",
        container_image="image",
    )

    with pytest.raises(MatrixRunError, match="inside workspace"):
        matrix._runtime_path(tmp_path / "outside", options)


def test_process_errors_are_actionable() -> None:
    assert "candidate failed" in str(MatrixRunError.process_failed("candidate", 2))
    assert "judge for profile failed" in str(MatrixRunError.judge_failed("profile", 2))
    assert "invalid JSON" in str(MatrixRunError.invalid_judgment("profile"))


def test_candidate_process_persists_trace_and_usage(monkeypatch, tmp_path) -> None:
    manifest = replace(
        load_matrix_manifest(MATRIX_PATH),
        artifact_root=tmp_path,
        runtime="process",
    )

    def fake_command(_profile, options):
        return ["candidate", str(options.final_path)]

    def fake_run(command, **_kwargs):
        Path(command[1]).write_text("candidate report", encoding="utf-8")
        return SimpleNamespace(
            returncode=0,
            stdout='{"usage": {"input_tokens": 11, "output_tokens": 7}}\n',
            stderr="",
        )

    monkeypatch.setattr(matrix, "_codex_command", fake_command)
    monkeypatch.setattr(matrix.subprocess, "run", fake_run)

    result = matrix._run_candidate(
        manifest,
        manifest.candidates[0],
        workspace=Path.cwd(),
        root=tmp_path,
    )

    assert result.final_message == "candidate report"
    assert result.input_tokens == INPUT_TOKENS
    assert result.output_tokens == OUTPUT_TOKENS
    assert result.trace_path.is_file()


def test_judge_process_returns_structured_assessment(monkeypatch, tmp_path) -> None:
    manifest = replace(
        load_matrix_manifest(MATRIX_PATH),
        artifact_root=tmp_path,
        runtime="process",
    )
    item = candidate(tmp_path, "sol-light")

    def fake_command(_profile, options):
        return ["judge", str(options.final_path)]

    def fake_run(command, **_kwargs):
        Path(command[1]).write_text(
            '{"overall_score": 0.75, "criteria": [], "strengths": [], '
            '"violations": [], "rationale": "ok"}',
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(matrix, "_codex_command", fake_command)
    monkeypatch.setattr(matrix.subprocess, "run", fake_run)

    result = matrix._judge_candidate(
        manifest,
        item,
        workspace=Path.cwd(),
        root=tmp_path,
        baseline={"elapsed_seconds": 2},
    )

    assert result.overall_score == JUDGE_SCORE
    assert result.assessment["rationale"] == "ok"
