"""Debug production support while preparing an uncurated benchmark workspace."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

from workspaces.data_engineering.agents.prod_support.agent import ProdSupportAgent
from workspaces.data_engineering.agents.prod_support.datasets import (
    ReplayAirflowFailureSource,
)
from workspaces.data_engineering.agents.prod_support.models import (
    ProdSupportOutcome,
    Region,
)
from workspaces.data_engineering.benchmarks.production_support import (
    collection_replay,
)
from workspaces.data_engineering.benchmarks.production_support.collection import (
    ProdSupportCaptureBundle,
    ProdSupportCollectionSources,
    collect_prod_support_data,
)


@dataclass(frozen=True, slots=True)
class DebugArtifacts:
    """Local artifacts produced by one production-backed debug run."""

    dataset: Path
    benchmark_root: Path
    outcome: ProdSupportOutcome
    capture: ProdSupportCaptureBundle


async def run_debug_day(
    sources: ProdSupportCollectionSources,
    operational_date: date,
    output_root: Path,
    *,
    regions: tuple[Region, ...] = (Region.US_01, Region.CA_02),
    captured_at: datetime | None = None,
) -> DebugArtifacts:
    """Capture production evidence, replay it, and scaffold review-only YAML."""
    if operational_date > datetime.now(UTC).date():
        message = "debug mode cannot capture a future operational date"
        raise ValueError(message)
    day_root = output_root / operational_date.isoformat()
    if day_root.exists():
        message = f"debug capture already exists; refusing to overwrite: {day_root}"
        raise FileExistsError(message)
    captured = captured_at or datetime.now(UTC)
    bundle = await collect_prod_support_data(
        sources,
        operational_date,
        day_root,
        regions=regions,
        captured_at=captured,
    )
    prompt_date = operational_date.strftime("%m/%d/%y")
    scope = (
        "US "
        if regions == (Region.US_01,)
        else "CA "
        if regions == (Region.CA_02,)
        else ""
    )
    prompt = f"Do {scope}prod support for {prompt_date}."
    outcome = await ProdSupportAgent(
        ReplayAirflowFailureSource(bundle.airflow),
        cluster_health=collection_replay.CapturedClusterHealthSource(
            bundle.cluster_health
        ),
        resource_discovery=collection_replay.CapturedResourceDiscoveryInvoker(
            bundle.resource_discovery
        ),
        clock=lambda: datetime.combine(
            operational_date,
            datetime.min.time(),
            tzinfo=UTC,
        ),
    ).investigate(prompt)
    benchmark_root = day_root / "benchmark"
    _write_scaffold(
        benchmark_root,
        operational_date,
        bundle,
        captured,
        regions,
    )
    return DebugArtifacts(bundle.airflow, benchmark_root, outcome, bundle)


def _write_scaffold(
    root: Path,
    operational_date: date,
    bundle: ProdSupportCaptureBundle,
    captured_at: datetime,
    regions: tuple[Region, ...],
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    suite_date = captured_at.date()
    scope_id = "-".join(region.value.casefold() for region in regions)
    case_id = f"prod-support-{scope_id}-operational-{operational_date.isoformat()}"
    dataset_uri = str(bundle.airflow)
    case = {
        "id": case_id,
        "reference_time": captured_at.astimezone(UTC).isoformat(),
        "prompt": f"Do prod support for {operational_date:%m/%d/%y}.",
        "operational_date": operational_date.isoformat(),
        "scope": [region.value for region in regions],
        "dataset_uri": dataset_uri,
        "operational_window": {
            "start": f"{operational_date.isoformat()}T05:00:00+00:00",
        },
        "airflow_base_urls": {
            "US-01": "https://airflow-us01.precisionlender.com",
            "CA-02": "https://airflow-ca02.precisionlender.com",
        },
        "candidate_inputs": [
            str(bundle.cluster_health),
            str(bundle.resource_discovery),
            str(bundle.compact_evidence),
            str(bundle.reporting_input),
        ],
        "reporting_contract_version": "3.0",
        "instructions": {
            "concurrent_leaf_handoffs": ["cluster", "airflow"],
            "nested_delegation": False,
            "triage_omissions": ["D2P", "MI3"],
        },
        "prohibit_agent_changes": True,
    }
    documents = {
        "suite.yaml": {
            "schema_version": 1,
            "suite_date": suite_date.isoformat(),
            "operational_date": operational_date.isoformat(),
            "directory_date_format": "MM-DD-YY",
            "status": "captured",
            "benchmark_id": "data_engineering.production_operations.prod_support",
            "description": (
                f"Uncurated prod-support capture for {operational_date.isoformat()}."
            ),
            "layers": {
                "capabilities": {"fixtures": [], "dimensions": []},
                "coordination": {"dimensions": []},
                "system": {"cases": []},
            },
        },
        "cases.yaml": {
            "schema_version": 1,
            "cases": [case],
            "daily_datasets": [
                {
                    "operational_date": operational_date.isoformat(),
                    "evidence_uri": dataset_uri,
                    "manifest_uri": str(bundle.manifest),
                    "captured_at": captured_at.astimezone(UTC).isoformat(),
                    "status": "captured",
                    "candidate_case_id": case_id,
                }
            ],
        },
    }
    for name, document in documents.items():
        (root / name).write_text(
            yaml.safe_dump(document, sort_keys=False),
            encoding="utf-8",
        )
