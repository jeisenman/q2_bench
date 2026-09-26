"""Security regression tests for isolated matrix execution."""

from dataclasses import replace
from pathlib import Path

import pytest

from adapters.inbound import MatrixRunError, matrix, matrix_runtime
from workspaces.data_engineering.benchmarks import load_matrix_run

ROOT = Path(__file__).parents[4]
AGENTS_PATH = ROOT / "src/workspaces/data_engineering/benchmarks/agent-manifest.yaml"
BENCHMARK_PATH = (
    ROOT
    / "src/workspaces/data_engineering/benchmarks/production_support"
    / "dates/09-25-26/evaluation.yaml"
)
CASES_PATH = BENCHMARK_PATH.with_name("cases.yaml")
CASE_ID = "prod-support-us-ca-2026-09-25"


def load_run():
    """Load the production-support matrix fixture."""
    return load_matrix_run(BENCHMARK_PATH, AGENTS_PATH, CASES_PATH, CASE_ID)


def test_candidate_workspace_rejects_symlinked_dataset(tmp_path) -> None:
    hidden = tmp_path / "hidden.json"
    hidden.write_text('{"secret": true}', encoding="utf-8")
    evidence = tmp_path / "var"
    evidence.mkdir()
    (evidence / "evidence.json").symlink_to(hidden)

    with (
        pytest.raises(MatrixRunError, match="may not contain symlinks"),
        matrix_runtime._candidate_workspace(
            tmp_path,
            (Path("var/evidence.json"),),
        ),
    ):
        pass


def test_codex_auth_source_rejects_symlinked_allowlisted_file(
    monkeypatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    hidden = tmp_path / "hidden.toml"
    hidden.write_text("[secret]\nvalue = true\n", encoding="utf-8")
    (codex_home / "config.toml").symlink_to(hidden)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    with (
        pytest.raises(MatrixRunError, match="authentication path is a symlink"),
        matrix_runtime._codex_auth_source(),
    ):
        pass


def test_codex_auth_source_rejects_symlinked_root(monkeypatch, tmp_path) -> None:
    actual_home = tmp_path / "actual-codex"
    actual_home.mkdir()
    linked_home = tmp_path / "linked-codex"
    linked_home.symlink_to(actual_home, target_is_directory=True)
    monkeypatch.setenv("CODEX_HOME", str(linked_home))

    with (
        pytest.raises(MatrixRunError, match="root may not be a symlink"),
        matrix_runtime._codex_auth_source(),
    ):
        pass


def test_candidate_rejects_symlinked_profile_output(tmp_path) -> None:
    loaded = load_run()
    manifest = replace(
        loaded,
        artifact_root=tmp_path,
        candidates=(loaded.candidates[0],),
    )
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / manifest.candidates[0].profile).symlink_to(
        outside,
        target_is_directory=True,
    )
    context = matrix._ExecutionContext(
        root=tmp_path,
        workspace=tmp_path / "workspace",
        auth_source=tmp_path / "auth",
    )

    with pytest.raises(MatrixRunError, match="output may not be a symlink"):
        matrix._run_candidate(manifest, manifest.candidates[0], context)


def test_adapter_rejects_symlinked_artifact_root(tmp_path) -> None:
    actual_root = tmp_path / "actual-output"
    actual_root.mkdir()
    linked_root = tmp_path / "linked-output"
    linked_root.symlink_to(actual_root, target_is_directory=True)
    manifest = replace(load_run(), artifact_root=linked_root)

    with pytest.raises(MatrixRunError, match="artifact root may not be a symlink"):
        matrix.MatrixInboundAdapter(tmp_path).run(manifest)


def test_output_write_rejects_candidate_created_symlink(tmp_path) -> None:
    profile_root = tmp_path / "profile"
    profile_root.mkdir()
    outside = tmp_path / "outside.log"
    outside.write_text("preserve", encoding="utf-8")
    trace = profile_root / "trace.jsonl"
    trace.symlink_to(outside)

    with pytest.raises(MatrixRunError, match="output may not be a symlink"):
        matrix._write_output(trace, "candidate output", profile_root)

    assert outside.read_text(encoding="utf-8") == "preserve"


def test_output_read_rejects_candidate_created_symlink(tmp_path) -> None:
    profile_root = tmp_path / "profile"
    profile_root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("hidden", encoding="utf-8")
    final = profile_root / "final.md"
    final.symlink_to(outside)

    with pytest.raises(MatrixRunError, match="output may not be a symlink"):
        matrix._read_output(final, profile_root)
