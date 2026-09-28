"""Parse and validate benchmark rubric applicability declarations."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path


class ApplicabilityError(ValueError):
    """Raised when a benchmark case has invalid applicability metadata."""

    @classmethod
    def invalid_mapping(cls, path: Path) -> ApplicabilityError:
        """Create an error for a non-boolean applicability mapping."""
        return cls(f"{path}: evaluation_applicability must be a boolean mapping")

    @classmethod
    def mismatched_criteria(
        cls,
        path: Path,
        missing: str,
        unknown: str,
    ) -> ApplicabilityError:
        """Create an error for incomplete or unknown criterion identifiers."""
        return cls(
            f"{path}: evaluation_applicability mismatch; "
            f"missing: {missing}; unknown: {unknown}"
        )


def parse_evaluation_applicability(
    case: Mapping[str, object],
    criterion_ids: tuple[str, ...],
    path: Path,
) -> tuple[tuple[str, bool], ...]:
    """Return an exact applicability map, defaulting legacy cases to applicable."""
    if "evaluation_applicability" not in case:
        return tuple((criterion_id, True) for criterion_id in criterion_ids)
    raw = case["evaluation_applicability"]
    if not isinstance(raw, dict) or not all(
        isinstance(key, str) and key.strip() and isinstance(value, bool)
        for key, value in raw.items()
    ):
        raise ApplicabilityError.invalid_mapping(path)
    expected = set(criterion_ids)
    actual = set(raw)
    if actual != expected:
        missing = ", ".join(sorted(expected - actual)) or "none"
        unknown = ", ".join(sorted(actual - expected)) or "none"
        raise ApplicabilityError.mismatched_criteria(path, missing, unknown)
    return tuple((key, value) for key, value in raw.items())
