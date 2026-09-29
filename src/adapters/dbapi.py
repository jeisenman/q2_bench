"""The DB-API surface warehouse adapters actually use.

Typing the driver this narrowly keeps `Any` out of the adapters while staying
honest about what they depend on: a cursor that executes a statement with
bound parameters and returns typed rows.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

DbApiValue = object
DbApiRow = Sequence[DbApiValue]


class DbApiCursor(Protocol):
    """The cursor operations a warehouse read needs."""

    @property
    def description(self) -> Sequence[Sequence[object]] | None:
        """Return column metadata for the last statement, if any."""
        ...

    def execute(
        self,
        statement: str,
        parameters: Mapping[str, object] | None = None,
    ) -> object:
        """Execute one statement with bound parameters."""
        ...

    def fetchall(self) -> Sequence[DbApiRow]:
        """Return every remaining row."""
        ...

    def close(self) -> None:
        """Release the cursor."""
        ...


class DbApiConnection(Protocol):
    """The connection operations a warehouse adapter needs."""

    def cursor(self) -> DbApiCursor:
        """Open a cursor."""
        ...

    def close(self) -> None:
        """Close the connection."""
        ...


class DuckDbConnection(Protocol):
    """DuckDB executes on the connection itself rather than through a cursor."""

    def execute(
        self,
        statement: str,
        parameters: Mapping[str, object] | None = None,
    ) -> DbApiCursor:
        """Execute one statement and return a result cursor."""
        ...

    def close(self) -> None:
        """Close the connection."""
        ...
