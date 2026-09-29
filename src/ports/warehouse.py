"""Typed contract for reading an analytics warehouse.

Snowflake, Databricks, and the DuckDB sandbox all satisfy this contract, so a
caller cannot tell which environment served a result. That is what makes a
sandbox run evidence about production rather than a separate universe.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol, TypeAlias

from domain.environments import Environment

SqlValue: TypeAlias = str | int | float | bool | None
Row: TypeAlias = tuple[SqlValue, ...]


def coerce_value(value: object) -> SqlValue:
    """Narrow one driver value to the port's declared scalar type.

    Drivers return vendor types (Decimal, datetime, UUID) that do not survive
    a cross-backend comparison. Rendering them as text keeps a sandbox row and
    a Snowflake row comparable, which is the whole point of the shared port.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        # format(..., "f") keeps the declared scale and avoids the scientific
        # notation that str() produces for values such as Decimal("0E-12").
        return format(value, "f")
    return str(value)


def coerce_row(values: Sequence[object]) -> Row:
    """Narrow one driver row to the port's declared value types."""
    return tuple(coerce_value(value) for value in values)


@dataclass(frozen=True, slots=True)
class Column:
    """One result column and the backend-reported type name."""

    name: str
    type_name: str


@dataclass(frozen=True, slots=True)
class SqlStatement:
    """A parameterized read-only statement.

    Parameters are bound by the driver rather than interpolated, which keeps
    values out of the SQL text for both injection safety and cache stability.
    """

    text: str
    parameters: Mapping[str, SqlValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject an empty statement at the boundary."""
        if not self.text.strip():
            message = "statement text must not be empty"
            raise ValueError(message)


@dataclass(frozen=True, slots=True)
class QueryResult:
    """Rows returned in a stable, backend-independent shape."""

    columns: tuple[Column, ...]
    rows: tuple[Row, ...]
    environment: Environment

    @property
    def column_names(self) -> tuple[str, ...]:
        """Return column names in result order."""
        return tuple(column.name for column in self.columns)

    def as_dicts(self) -> tuple[dict[str, SqlValue], ...]:
        """Return rows keyed by column name, for readable assertions."""
        names = self.column_names
        return tuple(dict(zip(names, row, strict=True)) for row in self.rows)


class WarehouseQueryError(RuntimeError):
    """Raised when a warehouse read cannot be completed."""


class WarehouseQuery(Protocol):
    """Run a read-only statement against one resolved environment."""

    @property
    def environment(self) -> Environment:
        """Return the environment this adapter is bound to."""
        ...

    async def fetch(self, statement: SqlStatement) -> QueryResult:
        """Return rows for a portable, read-only statement."""
        ...


class WarehouseSchema(Protocol):
    """Describe the tables an environment exposes."""

    async def tables(self, schema: str) -> Sequence[str]:
        """Return table names within one schema."""
        ...

    async def columns(self, schema: str, table: str) -> Sequence[Column]:
        """Return the typed columns of one table."""
        ...


class Warehouse(WarehouseQuery, WarehouseSchema, Protocol):
    """A warehouse that can be both queried and described.

    Every adapter implements both halves, so callers that need schema
    metadata alongside rows depend on one type rather than two.
    """
