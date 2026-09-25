"""Deterministic MLflow scorers for prod-support capability benchmarks."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from importlib import import_module
from typing import Protocol, cast

from workspaces.data_engineering.benchmarks import (
    failure_recall,
    regional_count_accuracy,
)

ScoreFunction = Callable[[dict[str, object], dict[str, object]], float]
TOKEN = re.compile(r"[a-z0-9-]+")


class NamedScorer(Protocol):
    """Minimal structural type returned by MLflow's scorer decorator."""

    name: str


def score_date_resolution(
    outputs: dict[str, object],
    expectations: dict[str, object],
) -> float:
    """Score operational-date and cutoff resolution using exact values."""
    actual = (outputs.get("operational_date"), outputs.get("failed_since"))
    expected = (
        expectations.get("expected_operational_date"),
        expectations.get("expected_since"),
    )
    return (
        sum(
            str(left) == str(right)
            for left, right in zip(actual, expected, strict=True)
        )
        / 2
    )


def score_failure_discovery(
    outputs: dict[str, object],
    expectations: dict[str, object],
) -> float:
    """Score exhaustive failure recall and exact regional counts."""
    actual_ids = set(_string_sequence(outputs.get("failure_ids")))
    expected_ids = set(_string_sequence(expectations.get("expected_failure_ids")))
    actual_counts = _integer_mapping(outputs.get("counts"))
    expected_counts = _integer_mapping(expectations.get("expected_counts"))
    return (
        failure_recall(actual_ids, expected_ids)
        + regional_count_accuracy(actual_counts, expected_counts)
    ) / 2


def score_log_classification(
    outputs: dict[str, object],
    expectations: dict[str, object],
) -> float:
    """Score one terminal-evidence classification exactly."""
    return float(
        str(outputs.get("classification"))
        == str(expectations.get("expected_classification"))
    )


def score_developer_message(
    outputs: dict[str, object],
    expectations: dict[str, object],
) -> float:
    """Score links, terminology, findings, and unsupported claims."""
    message = _message(outputs)
    checks = [
        *(
            value.casefold() in message
            for value in _string_mapping(
                expectations.get("required_cluster_links")
            ).values()
        ),
        *(
            _contains_terms(message, f"{key} {value}")
            for key, value in _string_mapping(
                expectations.get("required_terms")
            ).items()
        ),
        *(
            _contains_terms(message, finding)
            for finding in _string_sequence(expectations.get("required_findings"))
        ),
        *(
            not _contains_terms(message, claim)
            for claim in _string_sequence(expectations.get("prohibited_claims"))
        ),
    ]
    return _average(checks)


def score_prod_support_message(
    outputs: dict[str, object],
    expectations: dict[str, object],
) -> float:
    """Score channel structure, regional findings, follow-up, and safety."""
    message = _message(outputs)
    required = [
        str(expectations.get("required_heading", "")),
        *_string_sequence(expectations.get("required_regions")),
        *_string_sequence(expectations.get("required_us_findings")),
        *_string_sequence(expectations.get("required_ca_findings")),
        *_string_sequence(expectations.get("required_follow_on_message")),
    ]
    checks = [_contains_terms(message, item) for item in required if item]
    if expectations.get("mutation_policy") == "suggestion_only":
        checks.append(not bool(outputs.get("automatic_actions", [])))
    return _average(checks)


def build_prod_support_scorers() -> tuple[NamedScorer, ...]:
    """Build MLflow scorer wrappers for all component capabilities."""
    scorers = import_module("mlflow.genai.scorers")
    decorator = scorers.scorer
    functions: tuple[tuple[str, ScoreFunction], ...] = (
        ("date_resolution", score_date_resolution),
        ("failure_discovery", score_failure_discovery),
        ("log_classification", score_log_classification),
        ("developer_message", score_developer_message),
        ("prod_support_message", score_prod_support_message),
    )
    return tuple(
        cast("NamedScorer", decorator(name=name)(function))
        for name, function in functions
    )


def _message(outputs: Mapping[str, object]) -> str:
    return str(outputs.get("message", outputs.get("report", ""))).casefold()


def _contains_terms(message: str, expected: str) -> bool:
    return set(TOKEN.findall(expected.casefold())).issubset(TOKEN.findall(message))


def _string_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return ()
    return tuple(str(item) for item in value)


def _string_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _integer_mapping(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): int(cast("int", item)) for key, item in value.items()}


def _average(checks: list[bool]) -> float:
    return sum(checks) / len(checks) if checks else 1.0
