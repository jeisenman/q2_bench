from pathlib import Path

import pytest

from workspaces.data_engineering.benchmarks import (
    INSUFFICIENT_BENCHMARK_WARNING,
    BenchmarkCoverageError,
    benchmark_case_count,
    insufficient_benchmark_warning,
    prepend_benchmark_warning,
)

THRESHOLD_CASE_COUNT = 3
ROOT = Path(__file__).parents[5]


def _write_cases(root: Path, agent: str, count: int) -> None:
    path = root / agent / "dates/09-27-26/cases.yaml"
    path.parent.mkdir(parents=True)
    entries = "\n".join(f"  - id: case-{index}" for index in range(count))
    path.write_text(f"cases:\n{entries}\n", encoding="utf-8")


def test_counts_cases_across_an_agent_benchmark_directory(tmp_path: Path) -> None:
    _write_cases(tmp_path, "sample_agent", 2)
    second = tmp_path / "sample_agent/dates/09-28-26/cases.yaml"
    second.parent.mkdir(parents=True)
    second.write_text("cases:\n  - id: third\n", encoding="utf-8")

    assert benchmark_case_count("sample-agent", tmp_path) == THRESHOLD_CASE_COUNT


def test_missing_benchmark_has_zero_cases(tmp_path: Path) -> None:
    assert benchmark_case_count("missing-agent", tmp_path) == 0


def test_rejects_invalid_case_file(tmp_path: Path) -> None:
    path = tmp_path / "sample_agent/cases.yaml"
    path.parent.mkdir()
    path.write_text("cases: invalid\n", encoding="utf-8")

    with pytest.raises(BenchmarkCoverageError, match="cases must be a list"):
        benchmark_case_count("sample-agent", tmp_path)


def test_warning_uses_strict_fewer_than_three_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "workspaces.data_engineering.benchmarks.coverage.benchmark_case_count",
        lambda agent_id: 2 if agent_id == "under-tested" else 3,
    )

    assert (
        insufficient_benchmark_warning("under-tested") == INSUFFICIENT_BENCHMARK_WARNING
    )
    assert insufficient_benchmark_warning("threshold") is None
    assert prepend_benchmark_warning("result", INSUFFICIENT_BENCHMARK_WARNING) == (
        f"{INSUFFICIENT_BENCHMARK_WARNING}\n\nresult"
    )
    assert prepend_benchmark_warning("result", None) == "result"


def test_agent_architecture_diagram_tracks_current_case_counts() -> None:
    agents_root = ROOT / "src/workspaces/data_engineering/agents"
    diagram = (agents_root / "ARCHITECTURE.md").read_text(encoding="utf-8")
    agent_directories = sorted(
        path
        for path in agents_root.iterdir()
        if path.is_dir() and (path / "AGENTS.md").is_file()
    )

    for directory in agent_directories:
        agent_id = directory.name.replace("_", "-")
        count = benchmark_case_count(agent_id)
        assert f"{agent_id}<br/>{count} cases" in diagram
