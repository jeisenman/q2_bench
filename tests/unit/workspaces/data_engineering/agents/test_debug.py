import asyncio
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import yaml

from domain import AgentRequest, AgentResult
from workspaces.data_engineering.agents.prod_support import (
    AirflowFailure,
    Region,
    RegionalClusterHealth,
    run_debug_day,
)
from workspaces.data_engineering.benchmarks.production_support.collection import (
    ProdSupportCollectionSources,
)

CANDIDATE_INPUT_COUNT = 4


class FakeSource:
    async def discover_failures(self, since: datetime) -> tuple[AirflowFailure, ...]:
        assert since == datetime(2026, 9, 24, 5, tzinfo=UTC)
        return (
            AirflowFailure(
                Region.US_01,
                "l3-main-client",
                "run",
                "task",
                datetime(2026, 9, 25, 5, tzinfo=UTC),
                datetime(2026, 9, 25, 6, tzinfo=UTC),
                log="password=unsafe terminal failure",
            ),
        )

    async def fetch_log(self, failure: AirflowFailure) -> str:
        return failure.log


class FakeCluster:
    async def inspect_health(self, region: Region) -> RegionalClusterHealth:
        return RegionalClusterHealth(
            region=region,
            observed_at=datetime(2026, 9, 26, 16, tzinfo=UTC),
            pods_healthy=True,
            restart_count=0,
            keda_status="healthy",
        )


class FakeResources:
    async def run(self, request: AgentRequest) -> AgentResult:
        return AgentResult(
            output="not found",
            correlation_id=request.correlation_id,
            attributes=(
                ("identifier_kind", "client_id"),
                ("identifier_value", dict(request.attributes)["identifier_value"]),
                ("status", "not_found"),
                ("match_count", 0),
            ),
        )


def _sources() -> ProdSupportCollectionSources:
    return ProdSupportCollectionSources(
        FakeSource(),
        FakeCluster(),
        FakeResources(),
    )


def test_debug_day_captures_replays_and_scaffolds_unscored_schema(
    tmp_path: Path,
) -> None:
    artifacts = asyncio.run(
        run_debug_day(
            _sources(),
            date(2026, 9, 25),
            tmp_path,
            captured_at=datetime(2026, 9, 26, 16, tzinfo=UTC),
        )
    )

    assert "unsafe" not in artifacts.dataset.read_text(encoding="utf-8")
    assert len(artifacts.outcome.failures) == 1
    suite = yaml.safe_load(
        (artifacts.benchmark_root / "suite.yaml").read_text(encoding="utf-8")
    )
    cases = yaml.safe_load(
        (artifacts.benchmark_root / "cases.yaml").read_text(encoding="utf-8")
    )
    assert suite["status"] == "captured"
    assert suite["layers"]["system"]["cases"] == []
    assert "expected_failure_ids" not in cases["cases"][0]
    assert "expected_developer_message" not in cases["cases"][0]
    assert cases["cases"][0]["instructions"]["nested_delegation"] is False
    assert len(cases["cases"][0]["candidate_inputs"]) == CANDIDATE_INPUT_COUNT
    assert cases["daily_datasets"][0]["status"] == "captured"
    assert cases["daily_datasets"][0]["manifest_uri"].endswith(
        "collection_manifest.json"
    )
    assert not (artifacts.benchmark_root / "evaluation.yaml").exists()


def test_debug_day_rejects_future_capture(tmp_path: Path) -> None:
    future = date(2999, 1, 1)

    with pytest.raises(ValueError, match="future"):
        asyncio.run(run_debug_day(_sources(), future, tmp_path))


def test_debug_day_refuses_to_overwrite_capture(tmp_path: Path) -> None:
    (tmp_path / "2026-09-25").mkdir()

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        asyncio.run(run_debug_day(_sources(), date(2026, 9, 25), tmp_path))
