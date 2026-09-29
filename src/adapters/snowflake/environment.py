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
AUTHENTICATOR_SUFFIX: Final = "AUTHENTICATOR"
DEFAULT_SECRET_REF: Final = "snowflake/{environment}/password"
DEFAULT_AUTHENTICATOR: Final = "snowflake"
EXTERNAL_BROWSER: Final = "externalbrowser"
PASSWORDLESS_AUTHENTICATORS: Final = frozenset({EXTERNAL_BROWSER})
NAMED_AUTHENTICATORS: Final = frozenset(
    {DEFAULT_AUTHENTICATOR, EXTERNAL_BROWSER, "oauth", "snowflake_jwt"}
)


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
    def unknown_authenticator(cls, value: str) -> SnowflakeConfigurationError:
        """Return an error for an authenticator the connector will not accept."""
        named = ", ".join(sorted(NAMED_AUTHENTICATORS))
        return cls(
            f"unknown Snowflake authenticator {value!r}; use one of {named}, or "
            "an Okta account URL such as https://example.okta.com"
        )

    @classmethod
    def password_required(cls, authenticator: str) -> SnowflakeConfigurationError:
        """Return an error for a password-based mode reached without a secret."""
        return cls(
            f"the {authenticator!r} authenticator needs a password; resolve it "
            "through a SecretProvider before opening a connection"
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
    authenticator: str = DEFAULT_AUTHENTICATOR

    @property
    def requires_secret(self) -> bool:
        """Return whether this mode needs a password resolved at call time.

        Browser-based SSO delegates the credential to the identity provider,
        so there is no Snowflake password to look up. Asking a SecretProvider
        for one would fail on a secret that is not supposed to exist.
        """
        return self.authenticator.casefold() not in PASSWORDLESS_AUTHENTICATORS

    def connection_arguments(self, password: str | None) -> dict[str, str]:
        """Return driver arguments, with any secret supplied at call time."""
        arguments = {
            "account": self.account,
            "user": self.user,
            "role": self.role,
            "warehouse": self.warehouse,
            "database": self.database,
            "schema": self.schema,
        }
        if self.authenticator.casefold() != DEFAULT_AUTHENTICATOR:
            arguments["authenticator"] = self.authenticator
        if not self.requires_secret:
            return arguments
        if password is None:
            raise SnowflakeConfigurationError.password_required(self.authenticator)
        arguments["password"] = password
        return arguments


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
    authenticator = (
        os.environ.get(variable_name(environment, AUTHENTICATOR_SUFFIX), "").strip()
        or DEFAULT_AUTHENTICATOR
    )
    _require_known_authenticator(authenticator)
    return SnowflakeSettings(
        environment=environment,
        account=values["account"],
        user=values["user"],
        role=values["role"],
        warehouse=values["warehouse"],
        database=values["database"],
        schema=values["schema"],
        secret_ref=secret_ref,
        authenticator=authenticator,
    )


def _require_known_authenticator(value: str) -> None:
    """Reject an authenticator the connector would not understand."""
    if value.casefold() in NAMED_AUTHENTICATORS:
        return
    if value.casefold().startswith("https://"):
        return
    raise SnowflakeConfigurationError.unknown_authenticator(value)
