"""Read Snowflake through the Python connector, one environment at a time.

Statements pass the same portability rules the sandbox enforces, so a query
that works here works against DuckDB fixtures too. Reads are bound
parameters rather than interpolated text, and the connector runs on a worker
thread because it is synchronous.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from adapters.dbapi import DbApiConnection
from adapters.snowflake.environment import SnowflakeSettings, load_settings
from domain.environments import Environment
from domain.sql_portability import require_portable
from ports.secrets import SecretProvider
from ports.warehouse import (
    Column,
    QueryResult,
    Row,
    SqlStatement,
    WarehouseQueryError,
    coerce_row,
)

WRITE_PREFIXES = (
    "ALTER",
    "CREATE",
    "DELETE",
    "DROP",
    "GRANT",
    "INSERT",
    "MERGE",
    "REVOKE",
    "TRUNCATE",
    "UPDATE",
)


class SnowflakeUnavailableError(WarehouseQueryError):
    """Raised when the Snowflake connector is not installed."""

    @classmethod
    def missing_package(cls) -> SnowflakeUnavailableError:
        """Return an actionable installation error."""
        return cls(
            "snowflake-connector-python is required for dev, stage, and prod: "
            "uv sync --extra snowflake"
        )


class ReadOnlyViolationError(WarehouseQueryError):
    """Raised when a statement would modify a real warehouse."""

    @classmethod
    def for_statement(cls, keyword: str) -> ReadOnlyViolationError:
        """Return an error naming the rejected leading keyword."""
        return cls(
            f"{keyword} is a write statement; this port is read-only. Perform "
            "mutations through an explicit, authorized tool instead."
        )


def require_read_only(text: str) -> None:
    """Reject anything that is not a read, before it reaches the driver."""
    stripped = text.lstrip().lstrip("(").lstrip()
    keyword = stripped.split(maxsplit=1)[0].upper() if stripped else ""
    if keyword in WRITE_PREFIXES:
        raise ReadOnlyViolationError.for_statement(keyword)


class SnowflakeWarehouse:
    """A warehouse reader bound to one non-sandbox environment."""

    def __init__(
        self,
        settings: SnowflakeSettings,
        secrets: SecretProvider,
    ) -> None:
        """Create a reader; the connection opens lazily on first use."""
        self._settings = settings
        self._secrets = secrets
        self._connection: DbApiConnection | None = None
        self._lock = asyncio.Lock()

    @classmethod
    def for_environment(
        cls,
        environment: Environment,
        secrets: SecretProvider,
    ) -> SnowflakeWarehouse:
        """Build a reader from environment-scoped settings."""
        return cls(load_settings(environment), secrets)

    @property
    def environment(self) -> Environment:
        """Return the environment this adapter is bound to."""
        return self._settings.environment

    async def fetch(self, statement: SqlStatement) -> QueryResult:
        """Return rows for a portable, read-only statement."""
        require_portable(statement.text)
        require_read_only(statement.text)
        connection = await self._connect()
        return await asyncio.to_thread(self._fetch, connection, statement)

    def _fetch(
        self, connection: DbApiConnection, statement: SqlStatement
    ) -> QueryResult:
        cursor = connection.cursor()
        try:
            cursor.execute(statement.text, dict(statement.parameters) or None)
            description = cursor.description or ()
            columns = tuple(
                Column(name=str(item[0]), type_name=str(item[1]))
                for item in description
            )
            rows: tuple[Row, ...] = tuple(coerce_row(row) for row in cursor.fetchall())
        except Exception as error:
            message = f"Snowflake {self.environment.value} query failed: {error}"
            raise WarehouseQueryError(message) from error
        finally:
            cursor.close()
        return QueryResult(
            columns=columns,
            rows=rows,
            environment=self.environment,
        )

    async def tables(self, schema: str) -> Sequence[str]:
        """Return table names within one schema."""
        result = await self.fetch(
            SqlStatement(
                text=(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = %(schema)s ORDER BY table_name"
                ),
                parameters={"schema": schema.upper()},
            )
        )
        return tuple(str(row[0]) for row in result.rows)

    async def columns(self, schema: str, table: str) -> Sequence[Column]:
        """Return the typed columns of one table."""
        result = await self.fetch(
            SqlStatement(
                text=(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema = %(schema)s AND table_name = %(table)s "
                    "ORDER BY ordinal_position"
                ),
                parameters={"schema": schema.upper(), "table": table.upper()},
            )
        )
        return tuple(
            Column(name=str(row[0]), type_name=str(row[1])) for row in result.rows
        )

    async def _connect(self) -> DbApiConnection:
        async with self._lock:
            if self._connection is None:
                password = await self._secrets.get_secret(self._settings.secret_ref)
                self._connection = await asyncio.to_thread(
                    _open_connection,
                    self._settings,
                    password,
                )
            return self._connection

    async def close(self) -> None:
        """Close the connection when one was opened."""
        async with self._lock:
            if self._connection is not None:
                await asyncio.to_thread(self._connection.close)
                self._connection = None


def _open_connection(settings: SnowflakeSettings, password: str) -> DbApiConnection:
    # Deferred so the package imports without the optional provider SDK.
    try:
        import snowflake.connector  # noqa: PLC0415
    except ModuleNotFoundError as error:
        raise SnowflakeUnavailableError.missing_package() from error
    connection: DbApiConnection = snowflake.connector.connect(
        **settings.connection_arguments(password)
    )
    return connection
