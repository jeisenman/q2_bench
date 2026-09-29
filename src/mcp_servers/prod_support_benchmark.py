"""BenchBuilder integration helpers for the production-support MCP server."""

from __future__ import annotations

import os
from pathlib import Path

from workspaces.data_engineering.workflows.prod_support import (
    BenchmarkCaseArtifacts,
    build_daily_benchmark_case,
)
from workspaces.data_engineering.workflows.prod_support.models import (
    ProdSupportOutcome,
)

BENCHMARK_ROOT_ENV = "PROD_SUPPORT_BENCHMARK_ROOT"


def requests_benchmark_case(prompt: str) -> bool:
    """Return whether production support also requests benchmark construction."""
    normalized = " ".join(prompt.casefold().split())
    if any(
        phrase in normalized
        for phrase in ("do not build", "don't build", "without a benchmark")
    ):
        return False
    return "benchmark" in normalized and any(
        action in normalized for action in ("build", "create", "capture", "record")
    )


def capture_benchmark_case(
    outcome: ProdSupportOutcome,
    prompt: str,
    correlation_id: str,
) -> BenchmarkCaseArtifacts:
    """Capture one review-required draft under the configured local root."""
    root = Path(
        os.environ.get(
            BENCHMARK_ROOT_ENV,
            "var/benchmark_data/production_support",
        )
    )
    return build_daily_benchmark_case(outcome, prompt, correlation_id, root)
