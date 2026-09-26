"""Debug production support while preparing an uncurated benchmark workspace."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

from workspaces.data_engineering.agents.prod_support.agent import ProdSupportAgent
from workspaces.data_engineering.agents.prod_support.datasets import (
    ReplayAirflowFailureSource,
    capture_day,
)
from workspaces.data_engineering.agents.prod_support.models import ProdSupportOutcome
from workspaces.data_engineering.agents.prod_support.ports import AirflowFailureSource


@dataclass(frozen=True, slots=True)
class DebugArtifacts:
    """Local artifacts produced by one production-backed debug run."""

    dataset: Path
    benchmark_root: Path
    outcome: ProdSupportOutcome


async def run_debug_day(
    source: AirflowFailureSource,
    operational_date: date,
    output_root: Path,
    *,
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
    dataset = await capture_day(source, operational_date, day_root)
    prompt = f"Do prod support for {operational_date.isoformat()}."
    outcome = await ProdSupportAgent(
        ReplayAirflowFailureSource(dataset),
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
        dataset,
        captured_at or datetime.now(UTC),
    )
    return DebugArtifacts(dataset, benchmark_root, outcome)


def _write_scaffold(
    root: Path,
    operational_date: date,
    dataset: Path,
    captured_at: datetime,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    suite_date = captured_at.date()
    case_id = f"prod-support-us-ca-operational-{operational_date.isoformat()}"
    dataset_uri = str(dataset)
    case = {
        "id": case_id,
        "reference_time": captured_at.astimezone(UTC).isoformat(),
        "prompt": f"Do prod support for {operational_date.isoformat()}.",
        "operational_date": operational_date.isoformat(),
        "dataset_uri": dataset_uri,
        "expected_regions": ["US-01", "CA-02"],
        "expected_since": None,
        "expected_api_window": {},
        "expected_ui_window": {},
        "expected_cluster_links": {},
        "expected_failure_counts": {},
        "expected_failure_ids": [],
        "expected_diagnoses": {},
        "expected_developer_message": None,
        "expected_prod_support_message": None,
        "follow_on_message": None,
        "require_reported_dags_exist": True,
        "evidence_captured_at": {"US-01": None, "CA-02": None},
        "infrastructure_evidence_uris": {},
        "expected_infrastructure_statuses": {},
        "expected_oms_corroboration": {},
        "required_investigations": [],
        "omitted_from_data_internal": [],
        "resend_policy": {},
        "required_cluster_health_lines": [],
        "require_root_cause_per_reported_failure": None,
        "expected_remediation_policy": {},
        "expected_l3_main_graph_counts": {},
        "expected_active_dag_counts": {},
        "expected_active_l3_main_dag_counts": {},
        "expected_dag_ids": [],
        "airflow_base_urls": {
            "US-01": "https://airflow-us01.precisionlender.com",
            "CA-02": "https://airflow-ca02.precisionlender.com",
        },
        "candidate_inputs": [],
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
