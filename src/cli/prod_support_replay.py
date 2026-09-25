"""Run curated production-support cases against captured replay data."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from workspaces.data_engineering.agents.prod_support import (
    ProdSupportAgent,
    ProdSupportOutcome,
    ReplayAirflowFailureSource,
)


class ReplayCaseError(RuntimeError):
    """Raised when a replay case cannot be loaded or executed."""

    @classmethod
    def invalid_file(cls, path: Path, reason: str) -> ReplayCaseError:
        """Create an error identifying an invalid replay input file."""
        return cls(f"{path}: {reason}")

    @classmethod
    def unknown_case(cls, case_id: str) -> ReplayCaseError:
        """Create an error identifying an unknown benchmark case."""
        return cls(f"Unknown benchmark case: {case_id}")

    @classmethod
    def uncurated_case(cls, case_id: str) -> ReplayCaseError:
        """Create an error identifying a case without expected outcomes."""
        return cls(f"Benchmark case {case_id!r} is not curated for outcome evaluation")

    @classmethod
    def incomplete_case(cls, case_id: str, reason: str) -> ReplayCaseError:
        """Create an error identifying incomplete case configuration."""
        return cls(f"Benchmark case {case_id!r} {reason}")


@dataclass(frozen=True, slots=True)
class ReplayCase:
    """Prompt and deterministic clock for one benchmark case."""

    case_id: str
    prompt: str
    reference_time: datetime


def load_replay_case(cases_path: Path, case_id: str) -> ReplayCase:
    """Load one curated replay case from the benchmark catalog."""
    configured = _load_mapping(cases_path).get("cases")
    if not isinstance(configured, list):
        raise ReplayCaseError.invalid_file(cases_path, "cases must be a list")
    selected = next(
        (
            item
            for item in configured
            if isinstance(item, dict) and item.get("id") == case_id
        ),
        None,
    )
    if selected is None:
        raise ReplayCaseError.unknown_case(case_id)
    if not isinstance(selected.get("expected_failure_ids"), list) or not isinstance(
        selected.get("expected_diagnoses"), dict
    ):
        raise ReplayCaseError.uncurated_case(case_id)
    prompt = selected.get("prompt")
    reference_time = selected.get("reference_time")
    if not isinstance(prompt, str) or not isinstance(reference_time, str):
        raise ReplayCaseError.incomplete_case(
            case_id,
            "requires prompt and reference_time",
        )
    parsed_reference_time = datetime.fromisoformat(reference_time)
    if parsed_reference_time.tzinfo is None:
        raise ReplayCaseError.incomplete_case(
            case_id,
            "reference_time must include a timezone",
        )
    return ReplayCase(
        case_id=case_id,
        prompt=prompt,
        reference_time=parsed_reference_time,
    )


def run_replay_case(case: ReplayCase, dataset_path: Path) -> ProdSupportOutcome:
    """Execute one case against a deterministic captured Airflow dataset."""
    if not dataset_path.is_file():
        raise ReplayCaseError.invalid_file(
            dataset_path,
            "replay dataset does not exist",
        )
    source = ReplayAirflowFailureSource(dataset_path)
    agent = ProdSupportAgent(source, clock=lambda: case.reference_time)
    return asyncio.run(agent.investigate(case.prompt))


def write_recorded_outcome(outcome: ProdSupportOutcome, target: Path) -> Path:
    """Write an agent outcome in the format consumed by MLflow evaluation."""
    failures = {failure.failure_id: failure for failure in outcome.failures}
    diagnoses = []
    for diagnosis in outcome.diagnoses:
        failure = failures[diagnosis.failure_id]
        diagnoses.append(
            {
                "region": failure.region.value,
                "dag_id": failure.dag_id,
                "run_id": failure.run_id,
                "task_id": failure.task_id,
                "classification": diagnosis.kind.value,
                "confidence": diagnosis.confidence,
                "evidence": list(diagnosis.evidence),
            }
        )
    result = {
        "operational_date": outcome.operational_date.isoformat(),
        "failed_since": outcome.failed_since.isoformat(),
        "failure_count": len(outcome.failures),
        "automatic_actions": [],
        "diagnoses": diagnoses,
        "report": outcome.report,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def _load_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ReplayCaseError.invalid_file(
            path,
            "benchmark case file does not exist",
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ReplayCaseError.invalid_file(path, "expected a mapping")
    return raw
