"""Report benchmark-case coverage for MCP-exposed agents."""

from __future__ import annotations

from functools import cache
from importlib.resources import files
from pathlib import Path

import yaml

MINIMUM_BENCHMARK_CASES = 3
INSUFFICIENT_BENCHMARK_WARNING = "warning: this agent has not been tested thoroughly."
DEPRECATED_DIRECTORY = "deprecated"
_DIRECTORY_ALIASES = {
    "prod-support": "production_support",
    "prod_support": "production_support",
    "production-support": "production_support",
}


class BenchmarkCoverageError(ValueError):
    """Raised when benchmark case data has an invalid shape."""

    @classmethod
    def invalid_cases(cls, path: Path) -> BenchmarkCoverageError:
        """Identify a malformed benchmark case file."""
        return cls(f"{path}: cases must be a list")


def benchmark_case_count(agent_id: str, root: Path | None = None) -> int:
    """Count active public benchmark cases associated with one agent.

    Cases beneath ``deprecated/`` are excluded: they are retained as source
    data for new cases, not as evidence that current behavior is tested.
    """
    benchmark_root = root or Path(str(files("workspaces.data_engineering.benchmarks")))
    if root is None:
        return _bundled_benchmark_case_count(agent_id, benchmark_root)
    return _count_agent_cases(agent_id, benchmark_root)


@cache
def _bundled_benchmark_case_count(agent_id: str, root: Path) -> int:
    return _count_agent_cases(agent_id, root)


def deprecated_case_count(agent_id: str, root: Path | None = None) -> int:
    """Count retired cases retained as source data for new trace-derived cases."""
    benchmark_root = root or Path(str(files("workspaces.data_engineering.benchmarks")))
    directory = benchmark_root / DEPRECATED_DIRECTORY / _directory_name(agent_id)
    if not directory.is_dir():
        return 0
    return sum(_case_count(path) for path in sorted(directory.rglob("cases.yaml")))


def _directory_name(agent_id: str) -> str:
    return _DIRECTORY_ALIASES.get(agent_id, agent_id.replace("-", "_"))


def _count_agent_cases(agent_id: str, root: Path) -> int:
    directory = root / _directory_name(agent_id)
    if not directory.is_dir():
        return 0
    return sum(
        _case_count(path)
        for path in sorted(directory.rglob("cases.yaml"))
        if DEPRECATED_DIRECTORY not in path.relative_to(root).parts
    )


def _case_count(path: Path) -> int:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    cases = raw.get("cases") if isinstance(raw, dict) else None
    if not isinstance(cases, list):
        raise BenchmarkCoverageError.invalid_cases(path)
    return len(cases)


def insufficient_benchmark_warning(agent_id: str) -> str | None:
    """Return the MCP warning when an agent has fewer than three cases."""
    if benchmark_case_count(agent_id) < MINIMUM_BENCHMARK_CASES:
        return INSUFFICIENT_BENCHMARK_WARNING
    return None


def prepend_benchmark_warning(output: str, warning: str | None) -> str:
    """Prepend a warning without changing fully benchmarked agent output."""
    if warning is None:
        return output
    return f"{warning}\n\n{output}"
