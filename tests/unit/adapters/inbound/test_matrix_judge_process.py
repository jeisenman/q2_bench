import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from adapters.inbound import CandidateRun, matrix
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
JUDGE_SCORE = 0.75


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
