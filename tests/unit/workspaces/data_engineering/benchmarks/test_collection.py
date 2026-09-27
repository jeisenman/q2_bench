import asyncio
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from domain import AgentRequest, AgentResult
from workspaces.data_engineering.agents.prod_support import (
    AirflowFailure,
    Region,
    RegionalClusterHealth,
)
from workspaces.data_engineering.benchmarks.production_support import (
    collection_replay,
)
from workspaces.data_engineering.benchmarks.production_support.collection import (
    ProdSupportCollectionError,
    ProdSupportCollectionSources,
    collect_prod_support_data,
)

CLIENT_ID = "1f06da19-2f61-401c-a1b7-38902e4f3543"
EXPECTED_RECORD_COUNT = 2
EXPECTED_RESTART_COUNT = 2


class FakeAirflow:
    def __init__(self) -> None:
        self.regions: list[Region] = []
        self.fetched: list[str] = []

    async def discover_failures(
        self,
        since: datetime,
    ) -> tuple[AirflowFailure, ...]:
        del since
        raise AssertionError

    async def discover_region_failures(
        self,
        region: Region,
        since: datetime,
    ) -> tuple[AirflowFailure, ...]:
        assert since == datetime(2026, 9, 24, 5, tzinfo=UTC)
        self.regions.append(region)
        return (
            AirflowFailure(
                region,
                f"l3-main-{CLIENT_ID}",
                "run-d2p",
                "delivery_to_promise",
                datetime(2026, 9, 25, 5, tzinfo=UTC),
                datetime(2026, 9, 25, 6, tzinfo=UTC),
            ),
            AirflowFailure(
                region,
                f"l3-main-{CLIENT_ID}",
                "run-validation",
                "validate_event_bus_opportunities",
                datetime(2026, 9, 25, 6, tzinfo=UTC),
                datetime(2026, 9, 25, 7, tzinfo=UTC),
            ),
        )

    async def fetch_log(self, failure: AirflowFailure) -> str:
        self.fetched.append(failure.task_id)
        return "Missing opportunity snapshot(s)"

    async def has_success_within(
        self,
        failure: AirflowFailure,
        start_at: datetime,
        end_at: datetime,
    ) -> bool:
        del start_at, end_at
        return failure.task_id == "delivery_to_promise"


class FakeCluster:
    def __init__(self) -> None:
        self.regions: list[Region] = []

    async def inspect_health(self, region: Region) -> RegionalClusterHealth:
        self.regions.append(region)
        return RegionalClusterHealth(
            region=region,
            observed_at=datetime(2026, 9, 26, 15, tzinfo=UTC),
            pods_healthy=True,
            restart_count=0,
            keda_status="healthy",
        )


class FakeResources:
    def __init__(self) -> None:
        self.identifiers: list[str] = []

    async def run(self, request: AgentRequest) -> AgentResult:
        identifier = str(dict(request.attributes)["identifier_value"])
        self.identifiers.append(identifier)
        return AgentResult(
            output="unique",
            correlation_id=request.correlation_id,
            attributes=(
                ("identifier_value", identifier),
                ("status", "unique"),
                ("client_name", "Client A"),
                ("environment", "ca02"),
                ("reviewed_production_resend_url", "https://example.test/resend"),
                ("routing_source", "reviewed"),
                ("prod_support_ignore", False),
            ),
        )


def test_collects_compact_scope_aware_bundle(tmp_path: Path) -> None:
    airflow = FakeAirflow()
    cluster = FakeCluster()
    resources = FakeResources()
    target = tmp_path / "capture"

    bundle = asyncio.run(
        collect_prod_support_data(
            ProdSupportCollectionSources(airflow, cluster, resources),
            date(2026, 9, 25),
            target,
            regions=(Region.CA_02,),
            captured_at=datetime(2026, 9, 26, 16, tzinfo=UTC),
        )
    )

    assert airflow.regions == [Region.CA_02]
    assert airflow.fetched == [
        "delivery_to_promise",
        "validate_event_bus_opportunities",
    ]
    assert cluster.regions == [Region.CA_02]
    assert resources.identifiers == [CLIENT_ID]
    assert all(
        path.exists()
        for path in (
            bundle.airflow,
            bundle.cluster_health,
            bundle.resource_discovery,
            bundle.compact_evidence,
            bundle.reporting_input,
            bundle.manifest,
        )
    )
    compact = json.loads(bundle.compact_evidence.read_text(encoding="utf-8"))
    reporting = json.loads(bundle.reporting_input.read_text(encoding="utf-8"))
    manifest = json.loads(bundle.manifest.read_text(encoding="utf-8"))

    assert compact["summary"]["record_count"] == EXPECTED_RECORD_COUNT
    assert compact["summary"]["exact_log_records"] == EXPECTED_RECORD_COUNT
    assert compact["summary"]["triage_omitted_records"] == 1
    assert reporting["cluster_health"][0]["pods_healthy"] is True
    assert reporting["groups"][0]["omission_code"] == "D2P"
    assert manifest["regions"] == ["CA-02"]
    assert manifest["orchestration"]["nested_delegation"] is False


def test_replays_captured_cluster_and_resource_results(tmp_path: Path) -> None:
    cluster_path = tmp_path / "cluster.json"
    cluster_path.write_text(
        json.dumps(
            {
                "regions": [
                    {
                        "region": "CA-02",
                        "observed_at": "2026-09-26T16:00:00+00:00",
                        "application_healthy": None,
                        "pods_healthy": True,
                        "dags_parsing_healthy": None,
                        "active_dag_count": None,
                        "restart_count": 2,
                        "keda_status": "healthy",
                        "symptoms": [],
                        "warnings": ["recent restart"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    resource_path = tmp_path / "resources.json"
    resource_path.write_text(
        json.dumps(
            {
                "lookups": [
                    {
                        "client_id": CLIENT_ID,
                        "client_name": "Client A",
                        "match": "unique",
                        "environment": "ca02",
                        "reviewed_production_resend_url": None,
                        "routing_source": "reviewed",
                        "prod_support_ignore": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    cluster = collection_replay.CapturedClusterHealthSource(cluster_path)
    resources = collection_replay.CapturedResourceDiscoveryInvoker(resource_path)

    health = asyncio.run(cluster.inspect_health(Region.CA_02))
    found = asyncio.run(
        resources.run(
            AgentRequest(
                prompt="resolve",
                correlation_id="found",
                attributes=(
                    ("identifier_kind", "client_id"),
                    ("identifier_value", CLIENT_ID),
                ),
            )
        )
    )
    missing = asyncio.run(
        resources.run(
            AgentRequest(
                prompt="resolve",
                correlation_id="missing",
                attributes=(
                    ("identifier_kind", "client_id"),
                    ("identifier_value", "missing"),
                ),
            )
        )
    )

    assert health.restart_count == EXPECTED_RESTART_COUNT
    assert health.warnings == ("recent restart",)
    assert dict(found.attributes)["client_name"] == "Client A"
    assert dict(missing.attributes)["status"] == "not_found"
    with pytest.raises(collection_replay.CaptureReplayError, match="does not contain"):
        asyncio.run(cluster.inspect_health(Region.US_01))
    with pytest.raises(
        collection_replay.CaptureReplayError,
        match="identifier_value",
    ):
        asyncio.run(
            resources.run(
                AgentRequest(
                    prompt="resolve",
                    correlation_id="invalid",
                )
            )
        )


def test_collection_rejects_invalid_boundaries(tmp_path: Path) -> None:
    sources = ProdSupportCollectionSources(
        FakeAirflow(),
        FakeCluster(),
        FakeResources(),
    )

    with pytest.raises(ProdSupportCollectionError, match="must not be empty"):
        asyncio.run(
            collect_prod_support_data(
                sources,
                date(2026, 9, 25),
                tmp_path / "empty",
                regions=(),
            )
        )
    with pytest.raises(ProdSupportCollectionError, match="duplicates"):
        asyncio.run(
            collect_prod_support_data(
                sources,
                date(2026, 9, 25),
                tmp_path / "duplicate",
                regions=(Region.CA_02, Region.CA_02),
            )
        )
    with pytest.raises(ProdSupportCollectionError, match="timezone"):
        asyncio.run(
            collect_prod_support_data(
                sources,
                date(2026, 9, 25),
                tmp_path / "naive",
                captured_at=datetime(2026, 9, 26, 16),
            )
        )
