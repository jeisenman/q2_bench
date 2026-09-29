"""Translate production rows into safe, deterministic benchmark fixtures.

Real production data makes the best benchmark and cannot be committed. This
module rewrites it: identifiers become stable pseudonyms, free text is
redacted, and everything else keeps the shape the query under test depends
on. Two properties matter and both are enforced here.

Determinism: the same value with the same salt always yields the same
pseudonym, so a fixture rebuild produces an identical file and a case stays
reproducible.

Referential integrity: one client UUID maps to one pseudonym in every table,
so joins that worked in production still work in the fixture. A per-column
salt would break that, so the salt is per fixture set.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final
from uuid import UUID

DIGITS: Final = "0123456789"
LOWER: Final = "abcdefghijklmnopqrstuvwxyz"
REDACTED: Final = "[redacted]"
_UUID_PATTERN: Final = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class AnonymizationError(ValueError):
    """Raised when an anonymization policy cannot be applied safely."""

    @classmethod
    def unknown_column(cls, column: str, known: Sequence[str]) -> AnonymizationError:
        """Return an error for a policy naming a column that does not exist."""
        available = ", ".join(known) or "none"
        return cls(f"policy targets unknown column {column!r}; columns: {available}")

    @classmethod
    def uncovered_columns(cls, columns: Sequence[str]) -> AnonymizationError:
        """Return an error for columns no rule decides."""
        joined = ", ".join(columns)
        return cls(
            "every column needs an explicit strategy so nothing leaks by "
            f"default; undeclared: {joined}"
        )

    @classmethod
    def empty_salt(cls) -> AnonymizationError:
        """Return an error for a missing salt."""
        return cls("salt must not be empty; it makes pseudonyms unreproducible")

    @classmethod
    def not_a_uuid(cls, column: str, value: str) -> AnonymizationError:
        """Return an error for a UUID strategy applied to a non-UUID."""
        return cls(
            f"column {column!r} is not a UUID and cannot be pseudonymized: {value!r}"
        )


class Strategy(StrEnum):
    """How one column is transformed on its way into a fixture."""

    KEEP = "keep"
    """Preserve exactly. Only for values that carry no identifying content."""

    REDACT = "redact"
    """Replace with a fixed marker. For free text that may embed anything."""

    DROP = "drop"
    """Replace with NULL, preserving the column and its type."""

    PSEUDONYM = "pseudonym"
    """Stable surrogate preserving length and character class."""

    UUID = "uuid"
    """Stable surrogate UUID, so prefixes and joins still behave."""

    GENERALIZE = "generalize"
    """Reduce precision, e.g. a timestamp truncated to its date."""


@dataclass(frozen=True, slots=True)
class ColumnPolicy:
    """The strategy applied to one column."""

    column: str
    strategy: Strategy


@dataclass(frozen=True, slots=True)
class AnonymizationPolicy:
    """Every column's strategy for one table, plus the fixture-set salt."""

    salt: str
    columns: tuple[ColumnPolicy, ...]

    def __post_init__(self) -> None:
        """Reject a policy that cannot produce reproducible output."""
        if not self.salt.strip():
            raise AnonymizationError.empty_salt()

    def strategy_for(self, column: str) -> Strategy | None:
        """Return the strategy declared for one column, if any."""
        for policy in self.columns:
            if policy.column == column:
                return policy.strategy
        return None

    def require_total(self, columns: Sequence[str]) -> None:
        """Reject a policy that does not decide every column.

        Defaulting to KEEP would mean a new production column silently
        reaches a committed fixture, so an undeclared column is an error.
        """
        declared = {policy.column for policy in self.columns}
        unknown = sorted(declared.difference(columns))
        if unknown:
            raise AnonymizationError.unknown_column(unknown[0], columns)
        undeclared = [column for column in columns if column not in declared]
        if undeclared:
            raise AnonymizationError.uncovered_columns(undeclared)


def anonymize_value(
    value: str | None,
    strategy: Strategy,
    *,
    salt: str,
    column: str,
) -> str | None:
    """Apply one strategy to one value."""
    if value is None:
        return None
    if strategy is Strategy.UUID:
        return _pseudonym_uuid(value, salt=salt, column=column)
    if strategy is Strategy.PSEUDONYM:
        return _pseudonym_text(value, salt=salt)
    return _SIMPLE_STRATEGIES[strategy](value)


def anonymize_rows(
    columns: Sequence[str],
    rows: Sequence[Sequence[str | None]],
    policy: AnonymizationPolicy,
) -> tuple[tuple[str | None, ...], ...]:
    """Apply a total policy to every row, preserving column order."""
    policy.require_total(columns)
    strategies = [policy.strategy_for(column) or Strategy.REDACT for column in columns]
    return tuple(
        tuple(
            anonymize_value(
                value,
                strategy,
                salt=policy.salt,
                column=column,
            )
            for value, strategy, column in zip(row, strategies, columns, strict=True)
        )
        for row in rows
    )


def load_policy(raw: Mapping[str, object], salt: str) -> AnonymizationPolicy:
    """Build a policy from a benchmark case's declaration."""
    declared = raw.get("columns")
    if not isinstance(declared, dict) or not declared:
        message = "anonymization.columns must be a non-empty mapping"
        raise AnonymizationError(message)
    return AnonymizationPolicy(
        salt=salt,
        columns=tuple(
            ColumnPolicy(column=str(name), strategy=Strategy(str(value)))
            for name, value in sorted(declared.items())
        ),
    )


def _digest(value: str, salt: str) -> bytes:
    return hmac.new(
        salt.encode("utf-8"), value.encode("utf-8"), hashlib.sha256
    ).digest()


def _pseudonym_uuid(value: str, *, salt: str, column: str) -> str:
    if _UUID_PATTERN.match(value.strip()) is None:
        raise AnonymizationError.not_a_uuid(column, value)
    return str(UUID(bytes=_digest(value.strip().casefold(), salt)[:16], version=4))


def _pseudonym_text(value: str, *, salt: str) -> str:
    # Preserve length and character class so downstream parsing, padding, and
    # three-character prefix conventions behave as they do in production.
    digest = _digest(value, salt)
    rendered: list[str] = []
    for index, character in enumerate(value):
        source = digest[index % len(digest)]
        if character.isdigit():
            rendered.append(DIGITS[source % len(DIGITS)])
        elif character.isalpha():
            replacement = LOWER[source % len(LOWER)]
            rendered.append(replacement.upper() if character.isupper() else replacement)
        else:
            rendered.append(character)
    return "".join(rendered)


def _generalize(value: str) -> str:
    # Timestamps reduce to their date; anything else keeps only its prefix.
    if "T" in value:
        return value.split("T", 1)[0]
    if " " in value:
        return value.split(" ", 1)[0]
    return value[:3]


# Defined last: the table binds helpers declared above.
_SIMPLE_STRATEGIES: Final[dict[Strategy, Callable[[str], str | None]]] = {
    Strategy.KEEP: lambda value: value,
    Strategy.DROP: lambda _value: None,
    Strategy.REDACT: lambda _value: REDACTED,
    Strategy.GENERALIZE: _generalize,
}
