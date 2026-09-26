"""Compact replay evidence for token-efficient benchmark investigation."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

import click

from workspaces.data_engineering.agents.prod_support.classification import classify_log
from workspaces.data_engineering.agents.prod_support.datasets import (
    ReplayAirflowFailureSource,
)
from workspaces.data_engineering.agents.prod_support.evidence import summarize_task_log
from workspaces.data_engineering.agents.prod_support.models import EvidenceSource


@click.command("summarize-prod-support-evidence")
@click.option(
    "--dataset",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option("--start", "start_text", required=True)
@click.option("--end", "end_text", required=True)
def summarize_prod_support_evidence(
    dataset: Path,
    start_text: str,
    end_text: str,
) -> None:
    """Print one compact JSON record per exact replay task attempt."""
    start_at = _timestamp(start_text, "--start")
    end_at = _timestamp(end_text, "--end")
    if end_at <= start_at:
        message = "--end must be after --start"
        raise click.UsageError(message)
    source = ReplayAirflowFailureSource(dataset)
    failures = asyncio.run(source.discover_failures(start_at))
    for failure in failures:
        if not start_at <= failure.end_at < end_at:
            continue
        log = asyncio.run(source.fetch_log(failure))
        summary = summarize_task_log(log)
        diagnosis = classify_log(
            failure,
            log,
            source=EvidenceSource.AIRFLOW_EXACT_TASK_ATTEMPT,
        )
        click.echo(
            json.dumps(
                {
                    "classification": diagnosis.kind.value,
                    "confidence": diagnosis.confidence,
                    "dag_id": failure.dag_id,
                    "evidence": summary.excerpt.splitlines(),
                    "failure_id": failure.failure_id,
                    "log_characters": summary.original_char_count,
                    "log_retrieval": "exact_replay_task_attempt",
                    "log_status": summary.status.value,
                    "region": failure.region.value,
                    "run_id": failure.run_id,
                    "task_id": failure.task_id,
                    "try_number": failure.try_number,
                },
                sort_keys=True,
            )
        )


def _timestamp(value: str, option: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        message = f"{option} must be ISO-8601"
        raise click.UsageError(message) from error
    if parsed.tzinfo is None:
        message = f"{option} must include a timezone"
        raise click.UsageError(message)
    return parsed
