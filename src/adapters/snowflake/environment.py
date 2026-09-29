"""Resolve Snowflake connection settings per deployment environment.

Non-secret settings come from environment variables named per environment, so
one process can address dev, stage, and prod without ambiguity. The password
or private key is never read here: it is resolved through a ``SecretProvider``
at call time so it never lands in a dataclass, a log, or a trace.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

from domain.environments import Environment

SETTING_SUFFIXES: Final = (
    "ACCOUNT",
    "USER",
    "ROLE",
    "WAREHOUSE",
    "DATABASE",
    "SCHEMA",
)
SECRET_SUFFIX: Final = "SECRET_REF"
DEFAULT_SECRET_REF: Final = "snowflake/{environment}/password"


class SnowflakeConfigurationError(ValueError):
    """Raised when Snowflake settings for an environment are incomplete."""

    @classmethod
    def missing(
        cls,
        environment: Environment,
        names: tuple[str, ...],
    ) -> SnowflakeConfigurationError:
        """Return an error naming every missing variable."""
        joined = ", ".join(names)
        return cls(
            f"Snowflake {environment.value} configuration is incomplete; set: {joined}"
        )

    @classmethod
    def sandbox_unsupported(cls) -> SnowflakeConfigurationError:
        """Return an error for resolving Snowflake in the sandbox."""
        return cls(
            "the sandbox environment is served by DuckDB fixtures and has no "
            "Snowflake connection; resolve a DuckDbWarehouse instead"
        )


@dataclass(frozen=True, slots=True)
class SnowflakeSettings:
    """Non-secret Snowflake connection settings for one environment."""

    environment: Environment
    account: str
    user: str
    role: str
    warehouse: str
    database: str
    schema: str
    secret_ref: str

    def connection_arguments(self, password: str) -> dict[str, str]:
        """Return driver arguments, with the secret supplied at call time."""
        return {
            "account": self.account,
            "user": self.user,
            "password": password,
            "role": self.role,
            "warehouse": self.warehouse,
            "database": self.database,
            "schema": self.schema,
        }


def variable_name(environment: Environment, suffix: str) -> str:
    """Return the environment variable holding one setting."""
    return f"SNOWFLAKE_{environment.value.upper()}_{suffix}"


def load_settings(environment: Environment) -> SnowflakeSettings:
    """Read settings for one environment, failing fast on anything missing."""
    if environment is Environment.SANDBOX:
        raise SnowflakeConfigurationError.sandbox_unsupported()
    values: dict[str, str] = {}
    missing: list[str] = []
    for suffix in SETTING_SUFFIXES:
        name = variable_name(environment, suffix)
        value = os.environ.get(name, "").strip()
        if not value:
            missing.append(name)
        values[suffix.casefold()] = value
    if missing:
        raise SnowflakeConfigurationError.missing(environment, tuple(missing))
    secret_ref = os.environ.get(
        variable_name(environment, SECRET_SUFFIX), ""
    ).strip() or DEFAULT_SECRET_REF.format(environment=environment.value)
    return SnowflakeSettings(
        environment=environment,
        account=values["account"],
        user=values["user"],
        role=values["role"],
        warehouse=values["warehouse"],
        database=values["database"],
        schema=values["schema"],
        secret_ref=secret_ref,
    )
