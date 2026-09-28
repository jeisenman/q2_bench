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
    matrix_runtime,
)
from workspaces.data_engineering.benchmarks import load_matrix_run

ROOT = Path(__file__).parents[4]
AGENTS_PATH = ROOT / "src/workspaces/data_engineering/benchmarks/agent-manifest.yaml"
BENCHMARK_PATH = (
    ROOT
    / "src/workspaces/data_engineering/benchmarks/production_support"
    / "dates/09-27-26/evaluation.yaml"
)
CASES_PATH = BENCHMARK_PATH.with_name("cases.yaml")
CASE_ID = "handoff-bench-builder-agent-2026-09-26"
CANDIDATE_COUNT = 10
INPUT_TOKENS = 11
JUDGE_SCORE = 0.75
OUTPUT_TOKENS = 7


def load_run():
    return load_matrix_run(BENCHMARK_PATH, AGENTS_PATH, CASES_PATH, CASE_ID)


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
        load_run(),
        artifact_root=tmp_path,
        dataset=Path(
            "src/workspaces/data_engineering/benchmarks/production_support/"
            "dates/09-27-26/evidence/capture_manifest.json"
        ),
    )
    observed_baselines: dict[str, dict[str, object] | None] = {}
    (tmp_path / "comparison.json").write_text(
        '{"results": [{"profile": "sol-light", "elapsed_seconds": 2}]}',
        encoding="utf-8",
    )

    def fake_candidate(_manifest, profile, context):
        assert context.workspace != Path.cwd()
        assert context.auth_source.is_dir()
        return candidate(context.root, profile.profile)

    def fake_judge(
        _manifest,
        item,
        context,
        *,
        baseline,
    ):
        assert context.workspace != Path.cwd()
        assert context.auth_source.is_dir()
        observed_baselines[item.profile] = baseline
        return judged(context.root, item.profile)

    monkeypatch.setattr(matrix, "_run_candidate", fake_candidate)
    monkeypatch.setattr(matrix, "_judge_candidate", fake_judge)
    monkeypatch.setattr(matrix, "preflight_recorded_evidence", lambda *_args: None)

    results = MatrixInboundAdapter(Path.cwd()).run(manifest)

    assert len(results) == CANDIDATE_COUNT
    assert observed_baselines["sol-light"] == {
        "profile": "sol-light",
        "elapsed_seconds": 2,
    }
    comparison = json.loads((tmp_path / "comparison.json").read_text())
    assert len(comparison["results"]) == CANDIDATE_COUNT


def test_command_builds_container_and_process_variants(tmp_path) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir()
    output = tmp_path / "output"
    output.mkdir()
    auth_source = tmp_path / "auth"
    auth_source.mkdir()
    target = output / "final.md"
    profile = load_run().candidates[0]
    container = matrix_runtime._codex_command(
        profile,
        matrix_runtime._CommandOptions(
            workspace=workspace,
            sandbox="read-only",
            final_path=target,
            json_output=True,
            runtime="container",
            container_image="image",
            output_root=output,
            auth_source=auth_source,
        ),
    )
    process = matrix_runtime._codex_command(
        profile,
        matrix_runtime._CommandOptions(
            workspace=workspace,
            sandbox="read-only",
            final_path=target,
            json_output=False,
        ),
    )

    assert container[:2] == ["docker", "run"]
    assert container[container.index("--sandbox") + 1] == "danger-full-access"
    assert container[container.index("--profile") + 1] == "bedrock"
    assert "features.multi_agent=true" in container
    assert "--read-only" in container
    assert "--skip-git-repo-check" in container
    assert container[container.index("--cap-drop") + 1] == "ALL"
    assert "no-new-privileges" in container
    assert f"{workspace.resolve()}:/evaluation:ro" in container
    assert f"{output.resolve()}:/output" in container
    assert "AWS_PROFILE=benchmark" in container
    assert "AWS_SHARED_CREDENTIALS_FILE=/run/agent-auth/credentials" in container
    assert "--tmpfs" in container
    assert "/output/final.md" in container
    assert "--json" in container
    assert process[0] == "codex"


def test_trace_helpers_and_schema(tmp_path) -> None:
    events = matrix._json_lines(
        '{"usage": {"input_tokens": 3, "output_tokens": 2}}\ninvalid\n{}'
    )

    assert matrix._token_usage(events) == (3, 2)
    alternate = matrix._json_lines(
        '{"usage": {"prompt_tokens": 5, "completion_tokens": 4}}'
    )
    assert matrix._token_usage(alternate) == (5, 4)
    assert matrix._judge_schema()["type"] == "object"
    assert matrix._load_baselines(tmp_path / "missing.json") == {}
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")
    assert matrix._load_baselines(invalid) == {}
    target = tmp_path / "target.json"
    target.write_text('{"results": []}', encoding="utf-8")
    linked = tmp_path / "linked.json"
    linked.symlink_to(target)
    assert matrix._load_baselines(linked) == {}


def test_process_environment_is_allowlisted(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_CANARY", "must-not-pass")
    monkeypatch.setenv("PATH", "/bin")

    environment = matrix._command_environment("process")

    assert environment is not None
    assert environment["PATH"] == "/bin"
    assert "SECRET_CANARY" not in environment
    assert matrix._command_environment("container") is None


def test_container_path_must_be_inside_workspace(tmp_path) -> None:
    options = matrix_runtime._CommandOptions(
        workspace=tmp_path / "workspace",
        sandbox="read-only",
        final_path=tmp_path / "output",
        json_output=False,
        runtime="container",
        container_image="image",
    )

    with pytest.raises(MatrixRunError, match="inside workspace"):
        matrix_runtime._runtime_path(tmp_path / "outside", options)


def test_candidate_workspace_rejects_traversal(tmp_path) -> None:
    with (
        pytest.raises(MatrixRunError, match="workspace-relative"),
        matrix_runtime._candidate_workspace(tmp_path, (Path("../hidden"),)),
    ):
        pass


def test_candidate_workspace_stages_only_selected_dataset(tmp_path) -> None:
    dataset = Path("var/evidence.json")
    source = tmp_path / dataset
    source.parent.mkdir(parents=True)
    source.write_text('{"records": []}', encoding="utf-8")

    with matrix_runtime._candidate_workspace(tmp_path, (dataset,)) as workspace:
        staged = workspace / dataset
        assert staged.read_text(encoding="utf-8") == '{"records": []}'
        assert tuple(workspace.iterdir()) == (workspace / "var",)


def test_candidate_workspace_rejects_missing_dataset(tmp_path) -> None:
    with (
        pytest.raises(MatrixRunError, match="does not exist"),
        matrix_runtime._candidate_workspace(tmp_path, (Path("missing.json"),)),
    ):
        pass


def test_codex_auth_source_refreshes_temporary_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex"
    runtime = codex_home / ".runtime"
    runtime.mkdir(parents=True)
    (codex_home / "config.toml").write_text(
        '[model_providers.amazon-bedrock.aws]\nprofile = "source-profile"\n',
        encoding="utf-8",
    )
    (runtime / "netskope-ca-bundle.pem").write_text(
        "certificate",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setattr(
        matrix_runtime.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "AccessKeyId": "access",
                    "SecretAccessKey": "secret",
                    "SessionToken": "session",
                }
            ),
        ),
    )

    with matrix_runtime._codex_auth_source() as auth:
        credentials = (auth / ".runtime/aws-credentials").read_text(encoding="utf-8")
        assert "[benchmark]" in credentials
        assert "aws_access_key_id=access" in credentials
        assert not (auth / ".runtime/aws-sts-credentials.json").exists()


def test_codex_auth_source_rejects_empty_home(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))

    with (
        pytest.raises(MatrixRunError, match="no allowlisted"),
        matrix_runtime._codex_auth_source(),
    ):
        pass


def test_container_rejects_permissive_sandbox(tmp_path) -> None:
    options = matrix_runtime._CommandOptions(
        workspace=tmp_path,
        sandbox="danger-full-access",
        final_path=tmp_path / "final.md",
        json_output=False,
        runtime="container",
        container_image="image",
        output_root=tmp_path,
        auth_source=tmp_path,
    )

    with pytest.raises(MatrixRunError, match="sandbox must be read-only"):
        matrix_runtime._codex_command(load_run().candidates[0], options)


def test_container_requires_isolated_mounts(tmp_path) -> None:
    options = matrix_runtime._CommandOptions(
        workspace=tmp_path,
        sandbox="read-only",
        final_path=tmp_path / "final.md",
        json_output=False,
        runtime="container",
        container_image="image",
    )

    with pytest.raises(MatrixRunError, match="output_root and auth_source"):
        matrix_runtime._codex_command(load_run().candidates[0], options)


def test_aws_credentials_require_bedrock_profile(tmp_path) -> None:
    (tmp_path / "config.toml").write_text("", encoding="utf-8")

    with pytest.raises(MatrixRunError, match="missing an AWS profile"):
        matrix_runtime._write_aws_credentials(tmp_path)


def test_candidate_rejects_unsafe_profile(tmp_path) -> None:
    manifest = replace(load_run(), artifact_root=tmp_path)
    profile = replace(manifest.candidates[0], profile="../escape")
    context = matrix._ExecutionContext(tmp_path, tmp_path, tmp_path)

    with pytest.raises(MatrixRunError, match="unsafe matrix profile"):
        matrix._run_candidate(manifest, profile, context)


def test_process_errors_are_actionable() -> None:
    assert "candidate failed" in str(MatrixRunError.process_failed("candidate", 2))
    assert "judge for profile failed" in str(MatrixRunError.judge_failed("profile", 2))
    assert "invalid JSON" in str(MatrixRunError.invalid_judgment("profile"))


def test_candidate_process_persists_trace_and_usage(monkeypatch, tmp_path) -> None:
    manifest = replace(
        load_run(),
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
        matrix._ExecutionContext(Path.cwd(), tmp_path, tmp_path),
    )

    assert result.final_message == "candidate report"
    assert result.input_tokens == INPUT_TOKENS
    assert result.output_tokens == OUTPUT_TOKENS
    assert result.trace_path.is_file()
    assert result.trace_path.parent.parent.name == manifest.candidates[0].profile


def test_judge_process_returns_structured_assessment(monkeypatch, tmp_path) -> None:
    manifest = replace(
        load_run(),
        artifact_root=tmp_path,
        runtime="process",
    )
    item = candidate(tmp_path, "sol-light")

    def fake_command(_profile, options):
        return ["judge", str(options.final_path)]

    def fake_run(command, **_kwargs):
        criteria = [
            {"id": item.criterion_id, "score": 0.75, "rationale": "ok"}
            for item in manifest.rubric
        ]
        Path(command[1]).write_text(
            json.dumps(
                {
                    "overall_score": 0.1,
                    "criteria": criteria,
                    "strengths": [],
                    "violations": [],
                    "rationale": "ok",
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(matrix, "_codex_command", fake_command)
    monkeypatch.setattr(matrix.subprocess, "run", fake_run)

    result = matrix._judge_candidate(
        manifest,
        item,
        matrix._ExecutionContext(Path.cwd(), tmp_path, tmp_path),
        baseline={"elapsed_seconds": 2},
    )

    assert result.overall_score == JUDGE_SCORE
    assert result.assessment["rationale"] == "ok"
