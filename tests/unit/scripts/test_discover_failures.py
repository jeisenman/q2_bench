"""Tests for concurrent regional Airflow failure discovery."""

from __future__ import annotations

import importlib.util
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "src/workspaces/data_engineering/skills/prod-support/scripts/regional_queries.py"
)
EXPECTED_REGION_COUNT = 2


def load_module():
    """Load the skill script as a test module."""
    spec = importlib.util.spec_from_file_location(
        "prod_support_regional_queries",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
    return module


def test_regional_queries_overlap_and_return_in_region_order() -> None:
    module = load_module()
    started: set[str] = set()
    both_started = threading.Event()

    def fake_query(region, failed_since):
        assert failed_since == datetime(2026, 9, 29, 5, tzinfo=UTC)
        started.add(region)
        if len(started) == EXPECTED_REGION_COUNT:
            both_started.set()
        assert both_started.wait(timeout=1)
        return [{"region": region}]

    results = module.run_region_queries(
        ("US-01", "CA-02"),
        fake_query,
        datetime(2026, 9, 29, 5, tzinfo=UTC),
        max_workers=2,
    )

    assert started == {"US-01", "CA-02"}
    assert [item[0] for item in results] == ["US-01", "CA-02"]
    assert [item[1] for item in results] == [
        [{"region": "US-01"}],
        [{"region": "CA-02"}],
    ]
    assert all(item[2] is None for item in results)


def test_regional_queries_preserve_one_region_error() -> None:
    module = load_module()

    def fake_query(region, failed_since):
        del failed_since
        if region == "CA-02":
            raise RuntimeError
        return [{"region": region}]

    results = module.run_region_queries(
        ("US-01", "CA-02"),
        fake_query,
        datetime(2026, 9, 29, 5, tzinfo=UTC),
        max_workers=2,
    )

    assert results[0] == ("US-01", [{"region": "US-01"}], None)
    assert results[1][0] == "CA-02"
    assert results[1][1] is None
    assert isinstance(results[1][2], RuntimeError)


def test_regional_queries_reject_non_positive_worker_count() -> None:
    module = load_module()

    with pytest.raises(ValueError, match="at least 1"):
        module.run_region_queries(
            (),
            lambda region, failed_since: (region, failed_since),
            datetime(2026, 9, 29, 5, tzinfo=UTC),
            max_workers=0,
        )
