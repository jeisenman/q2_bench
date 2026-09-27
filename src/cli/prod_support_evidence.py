"""Compact replay evidence for token-efficient benchmark investigation."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import click

from workspaces.data_engineering.benchmarks.production_support.compact_evidence import (
    build_compact_evidence,
)


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
    result = build_compact_evidence(dataset, start_at, end_at)
    records = result.get("records")
    if not isinstance(records, tuple):
        message = "compact evidence records must be a tuple"
        raise TypeError(message)
    for record in records:
        click.echo(json.dumps(record, sort_keys=True))


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
