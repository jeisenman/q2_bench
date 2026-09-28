from pathlib import Path

import pytest

from adapters.inbound import MatrixRunError
from adapters.inbound.matrix_scoring import applicable_weighted_score
from workspaces.data_engineering.benchmarks import load_matrix_run

ROOT = Path(__file__).parents[4]
BENCHMARK = (
    ROOT
    / "src/workspaces/data_engineering/benchmarks/production_support"
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


def test_score_excludes_inapplicable_ordering_and_benchmark_quality() -> None:
    manifest = _manifest()
    criteria = [
        {
            "id": item.criterion_id,
            "score": (
                0.0
                if item.criterion_id in {"handoff_ordering", "benchmark_case_quality"}
                else 1.0
            ),
        }
        for item in manifest.rubric
    ]

    assert applicable_weighted_score(manifest, {"criteria": criteria}) == 1.0


def test_score_rejects_missing_applicable_criteria() -> None:
    with pytest.raises(MatrixRunError, match="judge omitted applicable criteria"):
        applicable_weighted_score(_manifest(), {"criteria": []})
