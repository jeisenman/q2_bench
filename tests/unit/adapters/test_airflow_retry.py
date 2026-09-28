"""Tests for exact Airflow retry payloads and response validation."""

from __future__ import annotations

import pytest

from adapters.airflow.retry import AirflowRetryError, execute_retry, plan_retry
from workspaces.data_engineering.agents.production_support.models import Region
from workspaces.data_engineering.agents.production_support.retry_models import (
    RetryBatch,
)


class FakeTransport:
    """Return the exact selected task and retain payloads."""

    def __init__(self, task_id: str = "task") -> None:
        self.payloads: list[dict[str, object]] = []
        self.task_id = task_id

    def request(
        self,
        config: object,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> object:
        del config, method, path
        self.payloads.append(dict(payload or {}))
        return {
            "task_instances": [
                {
                    "dag_id": "dag",
                    "dag_run_id": "run",
                    "task_id": self.task_id,
                    "state": "failed",
                }
            ]
        }


def test_plan_uses_safe_exact_clear_flags() -> None:
    transport = FakeTransport()
    batch = RetryBatch(Region.CA_02, "dag", "run", ("task",))

    references = plan_retry(batch, object(), transport)

    assert references[0].region is Region.CA_02
    assert transport.payloads[0] == {
        "dag_run_id": "run",
        "dry_run": True,
        "include_downstream": False,
        "include_future": False,
        "include_past": False,
        "include_upstream": False,
        "only_failed": True,
        "only_running": False,
        "reset_dag_runs": True,
        "task_ids": ["task"],
    }


def test_plan_can_select_successful_mapped_upstream_task() -> None:
    task_id = "ra_group.get_deposit_financial_statement_breakdown"
    transport = FakeTransport(task_id)
    batch = RetryBatch(
        Region.US_01,
        "dag",
        "run",
        (task_id,),
        only_failed=False,
    )

    plan_retry(batch, object(), transport)

    assert transport.payloads[0]["only_failed"] is False
    assert transport.payloads[0]["task_ids"] == [task_id]


def test_execute_revalidates_and_reads_state() -> None:
    transport = FakeTransport()
    batch = RetryBatch(Region.US_01, "dag", "run", ("task",))

    references = execute_retry(
        batch,
        "approval-1",
        object(),
        transport,
        lambda _task_id: {"state": "queued"},
    )

    assert [payload["dry_run"] for payload in transport.payloads] == [True, False]
    assert references[0].state == "queued"


def test_execute_requires_approval() -> None:
    with pytest.raises(AirflowRetryError, match="approval ID"):
        execute_retry(
            RetryBatch(Region.US_01, "dag", "run", ("task",)),
            "",
            object(),
            FakeTransport(),
            lambda _task_id: {"state": "failed"},
        )
