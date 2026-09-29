"""Serve warehouse reads from DuckDB over CSV fixtures.

This is the sandbox environment. Schemas mirror the real warehouse, the
compatibility macros cover the Snowflake scalar functions DuckDB lacks, and
everything the macros cannot cover is rejected by ``domain.sql_portability``
before it reaches any backend.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Final

from adapters.dbapi import DuckDbConnection
from domain.environments import Environment
from domain.sql_portability import require_portable
from ports.warehouse import (
    Column,
    QueryResult,
    Row,
    SqlStatement,
    WarehouseQueryError,
    coerce_row,
)

if TYPE_CHECKING:  # pragma: no cover - import-time typing only
    from adapters.duckdb.fixtures import FixtureSet

COMPAT_SQL: Final = Path(__file__).with_name("compat.sql")


class DuckDbUnavailableError(WarehouseQueryError):
    """Raised when the duckdb package is not installed."""

    @classmethod
    def missing_package(cls) -> DuckDbUnavailableError:
        """Return an actionable installation error."""
        return cls("duckdb is required for the sandbox environment: uv add duckdb")


class DuckDbWarehouse:
    """A deterministic warehouse backed by typed CSV fixtures."""

    def __init__(self, fixtures: FixtureSet) -> None:
        """Create the sandbox and load every fixture table eagerly."""
        self._fixtures = fixtures
        self._connection = _connect()
        self._install()

    @property
    def environment(self) -> Environment:
        """Return the sandbox environment."""
        return Environment.SANDBOX

    @property
    def fixture_digest(self) -> str:
        """Return the content digest of the loaded fixture set."""
        return self._fixtures.digest()

    def _install(self) -> None:
        self._connection.execute(COMPAT_SQL.read_text(encoding="utf-8"))
        for schema in self._fixtures.schemas:
            self._connection.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        for table in self._fixtures.tables:
            self._connection.execute(table.create_statement())
            self._connection.execute(
                f'COPY "{table.schema}"."{table.name}" '
                f"FROM '{table.data_file.as_posix()}' "
                "(FORMAT CSV, HEADER, NULLSTR '')"
            )

    async def fetch(self, statement: SqlStatement) -> QueryResult:
        """Return rows for a portable, read-only statement."""
        require_portable(statement.text)
        return await asyncio.to_thread(self._fetch, statement)

    def _fetch(self, statement: SqlStatement) -> QueryResult:
        try:
            cursor = self._connection.execute(
                statement.text,
                dict(statement.parameters) or None,
            )
        except Exception as error:
            message = f"sandbox query failed: {error}"
            raise WarehouseQueryError(message) from error
        description = cursor.description or ()
        columns = tuple(
            Column(name=str(item[0]), type_name=str(item[1])) for item in description
        )
        rows: tuple[Row, ...] = tuple(coerce_row(row) for row in cursor.fetchall())
        return QueryResult(
            columns=columns,
            rows=rows,
            environment=Environment.SANDBOX,
        )

    async def tables(self, schema: str) -> Sequence[str]:
        """Return table names within one fixture schema."""
        return tuple(
            table.name for table in self._fixtures.tables if table.schema == schema
        )

    async def columns(self, schema: str, table: str) -> Sequence[Column]:
        """Return the declared columns of one fixture table."""
        for candidate in self._fixtures.tables:
            if candidate.schema == schema and candidate.name == table:
                return tuple(
                    Column(name=column.name, type_name=column.type_name)
                    for column in candidate.columns
                )
        message = f"unknown sandbox table: {schema}.{table}"
        raise WarehouseQueryError(message)

    def close(self) -> None:
        """Release the in-memory database."""
        self._connection.close()


def _connect() -> DuckDbConnection:
    # Deferred so the package imports without duckdb installed; the sandbox
    # is the only environment that needs it.
    try:
        import duckdb  # noqa: PLC0415
    except ModuleNotFoundError as error:
        raise DuckDbUnavailableError.missing_package() from error
    connection: DuckDbConnection = duckdb.connect()
    return connection
