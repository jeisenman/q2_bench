from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from adapters.inbound import MatrixRunError, matrix_preflight
from workspaces.data_engineering.benchmarks import load_matrix_run

ROOT = Path(__file__).parents[4]
BENCHMARK = (
    ROOT
    / "src/workspaces/data_engineering/benchmarks/deprecated/production_support"
    / "dates/09-27-26/evaluation.yaml"
)
AGENTS = ROOT / "src/workspaces/data_engineering/benchmarks/agent-manifest.yaml"
CASES = BENCHMARK.with_name("cases.yaml")


def _manifest():
    return load_matrix_run(
        BENCHMARK,
        AGENTS,
        CASES,
        "prod-support-us-ca-operational-2026-09-26",
        ("sol-light",),
    )


def test_preflight_uses_the_isolated_container_before_model_use(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: list[str] = []

    def fake_run(command, **_kwargs):
        observed.extend(command)
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(matrix_preflight.subprocess, "run", fake_run)

    matrix_preflight.preflight_recorded_evidence(_manifest(), tmp_path)

    assert "--entrypoint" in observed
    assert "python3" in observed
    assert "compact_brief" in " ".join(observed)


def test_preflight_failure_invalidates_run_before_model_use(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        matrix_preflight.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1,
            stderr="ModuleNotFoundError: missing dependency\n",
        ),
    )

    with pytest.raises(
        MatrixRunError,
        match=r"preflight failed before model invocation.*missing dependency",
    ):
        matrix_preflight.preflight_recorded_evidence(_manifest(), tmp_path)


def test_preflight_skips_cases_without_compact_evidence(tmp_path: Path) -> None:
    manifest = replace(_manifest(), candidate_inputs=())

    matrix_preflight.preflight_recorded_evidence(manifest, tmp_path)
