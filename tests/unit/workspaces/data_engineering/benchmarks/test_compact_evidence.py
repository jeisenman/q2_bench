import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from workspaces.data_engineering.benchmarks.production_support import compact_brief
from workspaces.data_engineering.benchmarks.production_support.compact_brief import (
    build_report_brief,
)
from workspaces.data_engineering.benchmarks.production_support.compact_evidence import (
    build_compact_evidence,
    summary_record,
)

EXPECTED_EVENT_COUNT = 2


def test_compacts_logs_and_normalizes_retired_pod_warning(tmp_path: Path) -> None:
    dataset = tmp_path / "failures.json"
    dataset.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "region": "CA-02",
                        "dag_id": "dag",
                        "run_id": "run",
                        "task_id": "task",
                        "start_at": "2026-09-25T05:00:00+00:00",
                        "end_at": "2026-09-25T06:00:00+00:00",
                        "try_number": 2,
                        "log": ("progress\n" * 1_000) + "OOMKilled terminal",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    cluster = tmp_path / "cluster.json"
    cluster.write_text(
        json.dumps(
            {
                "captured_at": "2026-09-26T17:04:26Z",
                "regions": [
                    {
                        "region": "CA-02",
                        "application_health": {"scheduler": "healthy"},
                        "pods": {
                            "primary_pods_healthy": True,
                            "running_unready_count": 1,
                            "warning": "retired replica is unready",
                        },
                        "dags": {"active_count": 34, "parsing_status": "healthy"},
                        "keda_scaledobjects": {
                            "status": "access_denied",
                            "detail": "cannot list scaledobjects",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = build_compact_evidence(
        dataset,
        datetime(2026, 9, 25, 5, tzinfo=UTC),
        datetime(2026, 9, 26, 5, tzinfo=UTC),
        cluster_health=cluster,
    )

    record = result["records"][0]
    assert record["evidence"] == ("OOMKilled terminal",)
    assert record["log_characters"] > len("OOMKilled terminal")
    health = result["cluster_health"][0]
    assert health["state"] == "healthy"
    assert health["pods_healthy"] is True
    assert health["observed_at"] == "2026-09-26T17:04:26Z"
    assert "retired replica is unready" in health["warnings"]
    assert summary_record(result)["raw_logs_retained"] == 0


def test_compacts_policy_omissions_without_log_evidence(tmp_path: Path) -> None:
    dataset = tmp_path / "failures.json"
    dataset.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "region": "US-01",
                        "dag_id": "delivery_to_promise",
                        "run_id": "run",
                        "task_id": "delivery_to_promise",
                        "start_at": "2026-09-25T05:00:00+00:00",
                        "end_at": "2026-09-25T06:00:00+00:00",
                        "try_number": 1,
                        "triage_status": "omitted",
                        "log_retrieval": "omitted_by_policy",
                        "omission_code": "D2P",
                        "log": "",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    cluster = tmp_path / "cluster.json"
    cluster.write_text(
        json.dumps(
            {
                "captured_at": "2026-09-26T17:04:26+00:00",
                "regions": [
                    {
                        "region": "US-01",
                        "observed_at": "2026-09-26T17:04:00+00:00",
                        "state": "healthy",
                        "pods_healthy": True,
                        "restart_count": 0,
                        "keda_status": "healthy",
                        "symptoms": [],
                        "warnings": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    compact = build_compact_evidence(
        dataset,
        datetime(2026, 9, 25, 5, tzinfo=UTC),
        datetime(2026, 9, 26, 5, tzinfo=UTC),
        cluster_health=cluster,
    )
    brief = build_report_brief(compact, dataset)

    assert compact["summary"]["exact_log_records"] == 0
    assert compact["summary"]["triage_omitted_records"] == 1
    assert compact["records"][0]["log_status"] == "omitted"
    assert compact["records"][0]["evidence"] == ()
    assert compact["cluster_health"][0]["restart_count"] == 0
    assert brief["groups"][0]["root_cause"] == "triage omitted by policy"
    assert brief["groups"][0]["log_status_counts"] == {"omitted": 1}


def test_report_brief_groups_resend_counts_and_reviewed_route(
    tmp_path: Path,
) -> None:
    client_id = "1f06da19-2f61-401c-a1b7-38902e4f3543"
    dataset = tmp_path / "failures.json"
    dataset.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "region": "CA-02",
                        "dag_id": f"l3-main-{client_id}",
                        "run_id": "manual__2026-09-14T05:00:00+00:00",
                        "task_id": "validate_event_bus_opportunities",
                        "start_at": "2026-09-25T05:00:00+00:00",
                        "end_at": "2026-09-25T06:00:00+00:00",
                        "try_number": 2,
                        "log": (
                            "Missing opportunity snapshot(s)\n"
                            f"ClientId: {client_id}\n"
                            "OpportunityId: 00214d8d-e708-4d07-b181-fa6198bfbbb8\n"
                            "OpportunityId: 0045b7f8-19bd-4170-968d-34e1437d30a7"
                        ),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    discovery = tmp_path / "resources.json"
    discovery.write_text(
        json.dumps(
            {
                "lookups": [
                    {
                        "client_id": client_id,
                        "client_name": "Scotiabank",
                        "match": "unique",
                        "reviewed_production_resend_url": "https://example.test/resend",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    compact = build_compact_evidence(
        dataset,
        datetime(2026, 9, 25, 5, tzinfo=UTC),
        datetime(2026, 9, 26, 5, tzinfo=UTC),
    )

    brief = build_report_brief(
        compact,
        dataset,
        resource_discovery=discovery,
    )

    group = brief["groups"][0]
    assert group["client"] == "Scotiabank (1f0)"
    assert group["event_count"] == EXPECTED_EVENT_COUNT
    assert group["action_date"] == "2026-09-14"
    assert group["resend_supported"] is True
    assert group["resend_url"] == "https://example.test/resend"
    assert group["root_cause"] == "missing opportunity snapshots"


def test_report_brief_includes_fallback_context_and_omission_groups(
    tmp_path: Path,
) -> None:
    unresolved_id = "47322c85-71cf-45ea-9695-6bdcc1cc1ea9"
    dataset = tmp_path / "failures.json"
    records = [
        {
            "region": "US-01",
            "dag_id": "event_bus_to_payloads_historical",
            "run_id": "scheduled__2026-09-25T03:00:00+00:00",
            "task_id": "check_for_subscriber_client_errors",
            "start_at": "2026-09-25T05:00:00+00:00",
            "end_at": "2026-09-25T06:00:00+00:00",
            "try_number": 1,
            "log": "HTTP 404: log unavailable",
        },
        {
            "region": "CA-02",
            "dag_id": f"l3-main-{unresolved_id}",
            "run_id": "manual__2026-09-25T05:00:00+00:00",
            "task_id": f"client_specific_mi_3_raw_output_validation_{unresolved_id}",
            "start_at": "2026-09-25T05:00:00+00:00",
            "end_at": "2026-09-25T07:00:00+00:00",
            "try_number": 3,
            "log": "OOMKilled; truncated log",
        },
        {
            "region": "CA-02",
            "dag_id": "regional-job",
            "run_id": "manual_no_date",
            "task_id": "plain.task",
            "start_at": "2026-09-25T05:00:00+00:00",
            "end_at": "2026-09-25T08:00:00+00:00",
            "try_number": 1,
            "log": "plain terminal text",
        },
    ]
    dataset.write_text(json.dumps({"records": records}), encoding="utf-8")
    fallback = tmp_path / "fallback.json"
    fallback.write_text(
        json.dumps(
            {
                "region": "US-01",
                "dag_id": "canary",
                "task_id": "task",
                "runs": [
                    {"log_status": "unavailable", "state": "failed"},
                    {
                        "run_id": "prior",
                        "log_status": "available",
                        "state": "failed",
                        "log": "AirflowTaskTimeout",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    context = tmp_path / "context.json"
    context.write_text(
        json.dumps(
            {
                "evidence_type": "prior_day_carry_forward",
                "source_operational_date": "2026-09-24",
                "current_operational_date": "2026-09-25",
                "failure": {
                    "dag_id": f"l3-main-{unresolved_id}",
                    "task_id": "relationship_signals",
                },
                "airflow_evidence": ["exit code -9"],
                "oms_evidence": {"corroborating_memory_signal": False},
            }
        ),
        encoding="utf-8",
    )
    compact = build_compact_evidence(
        dataset,
        datetime(2026, 9, 25, 5, tzinfo=UTC),
        datetime(2026, 9, 26, 5, tzinfo=UTC),
    )

    brief = build_report_brief(
        compact,
        dataset,
        prior_run_logs=fallback,
        prior_context=context,
    )

    groups = {group["job"]: group for group in brief["groups"]}
    assert groups["subscriber checks"]["client"] == "Regional workload"
    assert groups["subscriber checks"]["omission_code"] == "Subscriber"
    assert groups["subscriber checks"]["log_status_counts"] == {"unavailable": 1}
    assert groups["MI3 raw-output validation"]["client"] == "Unresolved client (473)"
    assert groups["MI3 raw-output validation"]["omission_code"] == "MI3"
    assert groups["MI3 raw-output validation"]["log_status_counts"] == {"truncated": 1}
    assert groups["plain"].get("action_date") is None
    assert brief["dag_ids_by_region"]["CA-02"] == [
        f"l3-main-{unresolved_id}",
        "regional-job",
    ]
    assert brief["prior_run_fallback"]["root_cause"] == "Airflow task timeout"
    assert brief["prior_context"]["client_id"] == unresolved_id
    assert brief["prior_context"]["in_current_window"] is False


def test_report_brief_validates_inputs_and_cli_writes_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dataset = tmp_path / "failures.json"
    dataset.write_text(json.dumps({"records": []}), encoding="utf-8")
    compact = build_compact_evidence(
        dataset,
        datetime(2026, 9, 25, 5, tzinfo=UTC),
        datetime(2026, 9, 26, 5, tzinfo=UTC),
    )
    invalid_dataset = tmp_path / "invalid-dataset.json"
    invalid_dataset.write_text(json.dumps({"records": {}}), encoding="utf-8")
    invalid_discovery = tmp_path / "invalid-discovery.json"
    invalid_discovery.write_text(json.dumps({"lookups": {}}), encoding="utf-8")
    invalid_fallback = tmp_path / "invalid-fallback.json"
    invalid_fallback.write_text(json.dumps({"runs": {}}), encoding="utf-8")

    with pytest.raises(TypeError, match="records must be a list"):
        build_report_brief(compact, invalid_dataset)
    with pytest.raises(TypeError, match="compact records must be a list"):
        build_report_brief({"summary": {}, "records": {}}, dataset)
    with pytest.raises(TypeError, match="lookups must be a list"):
        build_report_brief(
            compact,
            dataset,
            resource_discovery=invalid_discovery,
        )
    with pytest.raises(TypeError, match="runs must be a list"):
        build_report_brief(compact, dataset, prior_run_logs=invalid_fallback)
    with pytest.raises(TypeError, match="expected an object"):
        compact_brief._mapping([], dataset)
    with pytest.raises(ValueError, match="timezone"):
        compact_brief._timestamp("2026-09-25T05:00:00")

    output = tmp_path / "compact.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "compact-brief",
            "--dataset",
            str(dataset),
            "--start",
            "2026-09-25T05:00:00Z",
            "--end",
            "2026-09-26T05:00:00Z",
            "--output",
            str(output),
        ],
    )
    compact_brief.main()

    printed = json.loads(capsys.readouterr().out)
    assert printed["summary"]["record_count"] == 0
    assert output.exists()
