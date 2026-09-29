from pathlib import Path
from typing import Any

import yaml

from workspaces.data_engineering.benchmarks import default_catalog

BENCHMARK_ROOT = (
    Path(__file__).parents[5]
    / "src/workspaces/data_engineering/benchmarks/python_upgrade"
)


def _yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_catalog_contains_python_upgrade_benchmark() -> None:
    benchmark = default_catalog().get(
        "data_engineering.pipeline_engineering.python_upgrade"
    )

    assert benchmark.display_name == "python-upgrade"
    assert benchmark.version == "1.0.0"


def test_python_upgrade_benchmark_covers_safe_and_unsafe_states() -> None:
    cases = _yaml(BENCHMARK_ROOT / "cases.yaml")["cases"]
    expectations = _yaml(BENCHMARK_ROOT / "hidden/case_expectations.yaml")["cases"]

    assert [case["id"] for case in cases] == [
        "safe-plan",
        "dependency-update",
        "unknown-support",
        "stale-apply",
    ]
    assert expectations[0]["apply_ready"] is True
    assert all(expectation["apply_ready"] is False for expectation in expectations[1:3])


def test_public_python_upgrade_cases_do_not_embed_expected_outcomes() -> None:
    text = (BENCHMARK_ROOT / "cases.yaml").read_text(encoding="utf-8")

    for key in ("apply_ready", "blockers:", "unknowns:", "error:"):
        assert key not in text
