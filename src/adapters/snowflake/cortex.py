"""Call Snowflake Cortex through the Python connector, per environment.

Cortex functions live in ``SNOWFLAKE.CORTEX`` and are reached with ordinary
SQL, so this adapter reuses the environment's connection. It deliberately
bypasses the warehouse port's portability rules, which reject Cortex on
purpose: inference belongs behind this port, where callers can see that the
result is not reproducible.
"""

from __future__ import annotations

import asyncio
from typing import cast

from adapters.dbapi import DbApiConnection, DbApiRow
from adapters.snowflake.environment import SnowflakeSettings, load_settings
from adapters.snowflake.warehouse import SnowflakeUnavailableError
from domain.environments import Environment
from ports.cortex import (
    CortexError,
    CortexRequest,
    CortexResponse,
    CortexUnavailableError,
)
from ports.secrets import SecretProvider

COMPLETE_SQL = "SELECT SNOWFLAKE.CORTEX.COMPLETE(%(model)s, %(prompt)s) AS completion"
COUNT_TOKENS_SQL = (
    "SELECT SNOWFLAKE.CORTEX.COUNT_TOKENS(%(model)s, %(text)s) AS token_count"
)


class SnowflakeCortex:
    """Run Cortex inference against one non-sandbox environment."""

    def __init__(
        self,
        settings: SnowflakeSettings,
        secrets: SecretProvider,
    ) -> None:
        """Create the adapter; the connection opens lazily on first use."""
        self._settings = settings
        self._secrets = secrets
        self._connection: DbApiConnection | None = None
        self._lock = asyncio.Lock()

    @classmethod
    def for_environment(
        cls,
        environment: Environment,
        secrets: SecretProvider,
    ) -> SnowflakeCortex:
        """Build a Cortex adapter from environment-scoped settings."""
        if environment is Environment.SANDBOX:
            message = (
                "the sandbox environment replays recorded Cortex responses; "
                "use RecordedCortex instead"
            )
            raise CortexUnavailableError(message)
        return cls(load_settings(environment), secrets)

    @property
    def environment(self) -> Environment:
        """Return the environment this adapter is bound to."""
        return self._settings.environment

    async def complete(self, request: CortexRequest) -> CortexResponse:
        """Return one live Cortex completion."""
        rows = await self._query(
            COMPLETE_SQL,
            {"model": request.model, "prompt": request.prompt},
        )
        if not rows or rows[0][0] is None:
            message = f"Cortex returned no completion for model {request.model!r}"
            raise CortexError(message)
        return CortexResponse(
            text=str(rows[0][0]),
            model=request.model,
            environment=self.environment,
            recorded=False,
        )

    async def count_tokens(self, model: str, text: str) -> int:
        """Return the tokenizer count without running inference."""
        rows = await self._query(COUNT_TOKENS_SQL, {"model": model, "text": text})
        if not rows or rows[0][0] is None:
            message = f"Cortex returned no token count for model {model!r}"
            raise CortexError(message)
        count = rows[0][0]
        if not isinstance(count, (int, str)):
            message = f"Cortex returned a non-numeric token count: {count!r}"
            raise CortexError(message)
        return int(count)

    async def _query(
        self,
        statement: str,
        parameters: dict[str, str],
    ) -> list[DbApiRow]:
        connection = await self._connect()
        return await asyncio.to_thread(self._run, connection, statement, parameters)

    def _run(
        self,
        connection: DbApiConnection,
        statement: str,
        parameters: dict[str, str],
    ) -> list[DbApiRow]:
        cursor = connection.cursor()
        try:
            cursor.execute(statement, parameters)
            return list(cursor.fetchall())
        except Exception as error:
            message = f"Cortex {self.environment.value} request failed: {error}"
            raise CortexError(message) from error
        finally:
            cursor.close()

    async def _connect(self) -> DbApiConnection:
        async with self._lock:
            if self._connection is None:
                password = (
                    await self._secrets.get_secret(self._settings.secret_ref)
                    if self._settings.requires_secret
                    else None
                )
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


def _open_connection(
    settings: SnowflakeSettings,
    password: str | None,
) -> DbApiConnection:
    # Deferred so the package imports without the optional provider SDK.
    try:
        import snowflake.connector  # noqa: PLC0415
    except ModuleNotFoundError as error:
        raise SnowflakeUnavailableError.missing_package() from error
    # SnowflakeConnection satisfies the operations DbApiConnection declares, but
    # its cursor() is generic over a cursor_class parameter, so mypy cannot match
    # it to the narrow Protocol. Cast the claim explicitly instead of letting the
    # adapter fall back to Any.
    connection = cast(
        "DbApiConnection",
        snowflake.connector.connect(**settings.connection_arguments(password)),
    )
    return connection
