"""Reject SQL that cannot mean the same thing in every environment.

A sandbox result is only evidence about production if the statement runs the
same way in both. Snowflake has constructs DuckDB cannot parse, and Cortex
calls are not deterministic at all. Both are rejected here, at the boundary
and in every environment, so a divergence surfaces when the statement is
written rather than when a benchmark silently disagrees with production.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

CORTEX_NAMESPACE: Final = re.compile(r"\bSNOWFLAKE\s*\.\s*CORTEX\s*\.", re.IGNORECASE)
_COMMENT_BLOCK: Final = re.compile(r"/\*.*?\*/", re.DOTALL)
_COMMENT_LINE: Final = re.compile(r"--[^\n]*")
_STRING_LITERAL: Final = re.compile(r"'(?:[^']|'')*'")


@dataclass(frozen=True, slots=True)
class PortabilityRule:
    """One construct that cannot be evaluated identically in every backend."""

    name: str
    pattern: re.Pattern[str]
    guidance: str


PORTABILITY_RULES: Final[tuple[PortabilityRule, ...]] = (
    PortabilityRule(
        name="cortex_call",
        pattern=CORTEX_NAMESPACE,
        guidance=(
            "Cortex is model inference and is never deterministic. Use the "
            "CortexInference port instead of embedding it in a query."
        ),
    ),
    PortabilityRule(
        name="variant_colon_path",
        pattern=re.compile(r"[A-Za-z_][A-Za-z0-9_]*\s*:\s*[A-Za-z_]"),
        guidance=(
            "Use arrow access such as payload->>'region' instead of payload:region."
        ),
    ),
    PortabilityRule(
        name="lateral_flatten",
        pattern=re.compile(r"\bLATERAL\s+FLATTEN\b", re.IGNORECASE),
        guidance="Use unnest(...) instead of LATERAL FLATTEN.",
    ),
    PortabilityRule(
        name="object_construct",
        pattern=re.compile(r"\bOBJECT_CONSTRUCT\s*\(", re.IGNORECASE),
        guidance="Build JSON with json_object(...) instead of OBJECT_CONSTRUCT.",
    ),
    PortabilityRule(
        name="dateadd_bare_part",
        pattern=re.compile(
            r"\bDATEADD\s*\(\s*(year|quarter|month|week|day|hour|minute|second)\b",
            re.IGNORECASE,
        ),
        guidance=(
            "DATEADD takes a bare date part that no macro can accept. Use "
            "an INTERVAL expression instead."
        ),
    ),
    PortabilityRule(
        name="nondeterministic_clock",
        pattern=re.compile(
            r"\b(CURRENT_TIMESTAMP|CURRENT_DATE|LOCALTIMESTAMP|SYSDATE|GETDATE|NOW)\b",
            re.IGNORECASE,
        ),
        guidance=(
            "Reading the clock makes a result depend on when it ran. Pass the "
            "operational window as a bound parameter instead."
        ),
    ),
    PortabilityRule(
        name="nondeterministic_value",
        pattern=re.compile(
            r"\b(RANDOM|RANDSTR|UUID_STRING|SEQ[1248])\s*\(", re.IGNORECASE
        ),
        guidance="Random and sequence values cannot be reproduced. Use fixture data.",
    ),
)


class SqlPortabilityError(ValueError):
    """Raised when a statement cannot be evaluated identically everywhere."""

    def __init__(self, violations: tuple[str, ...]) -> None:
        """Create an error listing every violated rule and its fix."""
        self.violations = violations
        joined = "; ".join(violations)
        super().__init__(f"statement is not portable across environments: {joined}")


def strip_noise(statement: str) -> str:
    """Remove comments and string literals so rules cannot match inside them."""
    without_blocks = _COMMENT_BLOCK.sub(" ", statement)
    without_lines = _COMMENT_LINE.sub(" ", without_blocks)
    return _STRING_LITERAL.sub("''", without_lines)


def portability_violations(statement: str) -> tuple[str, ...]:
    """Return one message per violated portability rule."""
    scanned = strip_noise(statement)
    return tuple(
        f"{rule.name}: {rule.guidance}"
        for rule in PORTABILITY_RULES
        if rule.pattern.search(scanned) is not None
    )


def require_portable(statement: str) -> None:
    """Raise when a statement would not mean the same thing in every backend."""
    if not statement.strip():
        message = "statement must not be empty"
        raise ValueError(message)
    violations = portability_violations(statement)
    if violations:
        raise SqlPortabilityError(violations)


def is_cortex_call(statement: str) -> bool:
    """Return whether a statement invokes Cortex inference."""
    return CORTEX_NAMESPACE.search(strip_noise(statement)) is not None
