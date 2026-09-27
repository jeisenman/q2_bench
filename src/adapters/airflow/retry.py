"""Exact Airflow clear-task planning and execution helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from typing import Protocol, cast
from urllib.parse import quote

from workspaces.data_engineering.agents.prod_support.models import Region
from workspaces.data_engineering.agents.prod_support.retry_models import (
    RetryBatch,
    RetryTaskReference,
)


class AirflowRetryError(ValueError):
    """Raised when an Airflow retry cannot be validated safely."""

    @classmethod
    def approval_required(cls) -> AirflowRetryError:
        """Return an error for retry execution without approval."""
        return cls("Airflow retry execution requires an approval ID")

    @classmethod
    def selection_mismatch(cls) -> AirflowRetryError:
        """Return an error for an inexact Airflow selection."""
        return cls("Airflow retry response did not match the exact request")


class AirflowRetryResponseTypeError(TypeError):
    """Raised when Airflow returns an invalid retry response shape."""

    @classmethod
    def missing_instances(cls) -> AirflowRetryResponseTypeError:
        """Return an error for a response without task instances."""
        return cls("Airflow retry response must contain task_instances")

    @classmethod
    def invalid_state(cls) -> AirflowRetryResponseTypeError:
        """Return an error for an invalid task state response."""
        return cls("Airflow retry state response must be an object")


class RetryTransport(Protocol):
    """Transport shape required by the retry helper."""

    def request(
        self,
        config: object,
        method: str,
        path: str,
        payload: Mapping[str, object] | None = None,
    ) -> object:
        """Return one decoded Airflow response."""


class AirflowRetryMixin:
    """Add approval-gated retries to an Airflow evidence source."""

    _transport: object

    def _config_for(self, region: Region) -> object:
        raise NotImplementedError

    async def plan_retry(
        self,
        batch: RetryBatch,
    ) -> tuple[RetryTaskReference, ...]:
        """Return Airflow's exact dry-run clear selection."""
        config = self._config_for(batch.region)
        transport = cast(RetryTransport, self._transport)
        return await asyncio.to_thread(plan_retry, batch, config, transport)

    async def execute_retry(
        self,
        batch: RetryBatch,
        approval_id: str,
    ) -> tuple[RetryTaskReference, ...]:
        """Clear approved tasks and return immediate state read-back."""
        config = self._config_for(batch.region)
        transport = cast(RetryTransport, self._transport)

        def read_state(task_id: str) -> object:
            path = (
                f"/api/v1/dags/{quote(batch.dag_id, safe='')}/dagRuns/"
                f"{quote(batch.run_id, safe='')}/taskInstances/"
                f"{quote(task_id, safe='')}"
            )
            return transport.request(config, "GET", path)

        return await asyncio.to_thread(
            execute_retry,
            batch,
            approval_id,
            config,
            transport,
            read_state,
        )


def plan_retry(
    batch: RetryBatch,
    config: object,
    transport: RetryTransport,
) -> tuple[RetryTaskReference, ...]:
    """Return Airflow's validated dry-run task selection."""
    response = transport.request(
        config,
        "POST",
        _clear_path(batch.dag_id),
        _payload(batch, dry_run=True),
    )
    return _references(response, batch)


def execute_retry(
    batch: RetryBatch,
    approval_id: str,
    config: object,
    transport: RetryTransport,
    state_reader: Callable[[str], object],
) -> tuple[RetryTaskReference, ...]:
    """Repeat validation, clear exact tasks, and read their states back."""
    if not approval_id.strip():
        raise AirflowRetryError.approval_required()
    plan_retry(batch, config, transport)
    response = transport.request(
        config,
        "POST",
        _clear_path(batch.dag_id),
        _payload(batch, dry_run=False),
    )
    _references(response, batch)
    return tuple(
        _state_reference(batch, task_id, state_reader(task_id))
        for task_id in batch.task_ids
    )


def _clear_path(dag_id: str) -> str:
    return f"/api/v1/dags/{quote(dag_id, safe='')}/clearTaskInstances"


def _payload(batch: RetryBatch, *, dry_run: bool) -> dict[str, object]:
    return {
        "dag_run_id": batch.run_id,
        "dry_run": dry_run,
        "include_downstream": False,
        "include_future": False,
        "include_past": False,
        "include_upstream": False,
        "only_failed": True,
        "only_running": False,
        "reset_dag_runs": True,
        "task_ids": list(batch.task_ids),
    }


def _references(
    response: object,
    batch: RetryBatch,
) -> tuple[RetryTaskReference, ...]:
    if not isinstance(response, dict) or not isinstance(
        response.get("task_instances"),
        list,
    ):
        raise AirflowRetryResponseTypeError.missing_instances()
    items = tuple(item for item in response["task_instances"] if isinstance(item, dict))
    selected = {
        str(item.get("task_id"))
        for item in items
        if item.get("dag_id") == batch.dag_id and item.get("dag_run_id") == batch.run_id
    }
    expected = set(batch.task_ids)
    if selected != expected or len(items) != len(expected):
        raise AirflowRetryError.selection_mismatch()
    return tuple(
        RetryTaskReference(
            batch.region,
            batch.dag_id,
            batch.run_id,
            task_id,
            str(
                next(item.get("state") for item in items if item["task_id"] == task_id)
            ),
        )
        for task_id in batch.task_ids
    )


def _state_reference(
    batch: RetryBatch,
    task_id: str,
    response: object,
) -> RetryTaskReference:
    if not isinstance(response, dict):
        raise AirflowRetryResponseTypeError.invalid_state()
    return RetryTaskReference(
        batch.region,
        batch.dag_id,
        batch.run_id,
        task_id,
        str(response.get("state", "unknown")),
    )
