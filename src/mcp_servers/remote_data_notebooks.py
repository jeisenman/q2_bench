"""Build deterministic notebooks for allowlisted remote data targets."""

from __future__ import annotations

import json
from dataclasses import dataclass

from adapters.outbound.data_engineering import (
    ADLS_TARGETS,
    DATABRICKS_TARGETS,
    AdlsEnvironment,
    SnowflakeEnvironment,
)

MAX_NOTEBOOK_LIMIT = 10_000
SUPPORTED_ADLS_FORMATS = frozenset({"csv", "delta", "json", "parquet"})


class RemoteDataNotebookError(ValueError):
    """Raised when a remote-data notebook request is unsafe or unsupported."""

    @classmethod
    def allowed_values(
        cls,
        label: str,
        values: tuple[str, ...],
    ) -> RemoteDataNotebookError:
        """Return an error describing an explicit allowlist."""
        return cls(f"{label} must be one of: {', '.join(values)}")

    @classmethod
    def empty(cls, label: str) -> RemoteDataNotebookError:
        """Return an error for a required blank value."""
        return cls(f"{label} must not be empty")

    @classmethod
    def invalid_limit(cls) -> RemoteDataNotebookError:
        """Return an error for an unsafe preview row limit."""
        return cls(f"limit must be between 1 and {MAX_NOTEBOOK_LIMIT}")

    @classmethod
    def mutating_sql(cls) -> RemoteDataNotebookError:
        """Return an error for SQL outside the read-only subset."""
        return cls(
            "statement must be a read-only SELECT, WITH, SHOW, or DESCRIBE query"
        )


@dataclass(frozen=True, slots=True)
class NotebookPayload:
    """A Databricks source notebook and its resolved non-secret target."""

    target: str
    source: str


def build_databricks_notebook(platform: str, code: str) -> NotebookPayload:
    """Return Databricks source boilerplate for a DE or RA workspace."""
    normalized = platform.strip().lower()
    try:
        target = DATABRICKS_TARGETS[normalized]
    except KeyError as error:
        raise RemoteDataNotebookError.allowed_values(
            "platform",
            tuple(sorted(DATABRICKS_TARGETS)),
        ) from error
    _require_text(code, "code")
    source = "\n".join(
        (
            "# Databricks notebook source",
            "# MAGIC %md",
            f"# MAGIC # Remote data query: {target.name}",
            "# MAGIC Generated query boilerplate. Review before running.",
            "",
            "# COMMAND ----------",
            "",
            code.strip(),
            "",
        )
    )
    return NotebookPayload(target=target.name, source=source)


def build_adls_notebook(
    environment: str,
    container: str,
    path: str,
    file_format: str,
    limit: int,
) -> NotebookPayload:
    """Return a bounded Spark notebook for one allowlisted ADLS location."""
    try:
        target = ADLS_TARGETS[AdlsEnvironment(environment)]
    except ValueError as error:
        raise RemoteDataNotebookError.allowed_values(
            "environment",
            tuple(item.value for item in AdlsEnvironment),
        ) from error
    _require_text(container, "container")
    _require_text(path, "path")
    normalized_format = file_format.strip().lower()
    if normalized_format not in SUPPORTED_ADLS_FORMATS:
        raise RemoteDataNotebookError.allowed_values(
            "file_format",
            tuple(sorted(SUPPORTED_ADLS_FORMATS)),
        )
    _validate_limit(limit)
    uri = (
        f"abfss://{container.strip()}@{target.account_name}.dfs.core.windows.net/"
        f"{path.strip().lstrip('/')}"
    )
    source = "\n".join(
        (
            "# Databricks notebook source",
            "# MAGIC %md",
            f"# MAGIC # ADLS query: {environment}",
            "# MAGIC Read-only bounded preview.",
            "",
            "# COMMAND ----------",
            "",
            f"adls_uri = {json.dumps(uri)}",
            f"data = spark.read.format({json.dumps(normalized_format)}).load(adls_uri)",
            f"display(data.limit({limit}))",
            "",
        )
    )
    return NotebookPayload(target=target.account_name, source=source)


def build_snowflake_notebook(
    environment: str,
    statement: str,
    limit: int,
) -> NotebookPayload:
    """Return a connector notebook for one allowlisted Snowflake environment."""
    try:
        resolved = SnowflakeEnvironment(environment)
    except ValueError as error:
        raise RemoteDataNotebookError.allowed_values(
            "environment",
            tuple(item.value for item in SnowflakeEnvironment),
        ) from error
    _require_text(statement, "statement")
    _validate_read_only_sql(statement)
    _validate_limit(limit)
    prefix = f"SNOWFLAKE_{resolved.value.upper()}"
    source = "\n".join(
        (
            "# Databricks notebook source",
            "# MAGIC %md",
            f"# MAGIC # Snowflake query: {resolved.value}",
            "# MAGIC Credentials are read from environment variables at runtime.",
            "",
            "# COMMAND ----------",
            "",
            "import os",
            "import snowflake.connector",
            "",
            "connection = snowflake.connector.connect(",
            f'    account=os.environ["{prefix}_ACCOUNT"],',
            f'    user=os.environ["{prefix}_USER"],',
            f'    password=os.environ["{prefix}_PASSWORD"],',
            ")",
            "try:",
            "    with connection.cursor() as cursor:",
            f"        cursor.execute({json.dumps(statement.strip())})",
            f"        rows = cursor.fetchmany({limit})",
            "        display(rows)",
            "finally:",
            "    connection.close()",
            "",
        )
    )
    return NotebookPayload(target=resolved.value, source=source)


def _require_text(value: str, label: str) -> None:
    if not value.strip():
        raise RemoteDataNotebookError.empty(label)


def _validate_limit(limit: int) -> None:
    if not 1 <= limit <= MAX_NOTEBOOK_LIMIT:
        raise RemoteDataNotebookError.invalid_limit()


def _validate_read_only_sql(statement: str) -> None:
    first_token = statement.lstrip().split(maxsplit=1)[0].lower()
    if first_token not in {"select", "show", "describe", "with"}:
        raise RemoteDataNotebookError.mutating_sql()
