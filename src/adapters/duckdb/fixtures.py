"""Load CSV fixtures into typed DuckDB tables that mirror warehouse schemas.

CSV is only the storage format. Every column is declared explicitly, so the
table a query sees is fully typed and inference never runs: a fixture edit
cannot silently change a column's type. The fixture set carries a content
digest so a benchmark case pins the exact data it was written against.
"""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import yaml

SCHEMA_FILE: Final = "schema.yaml"
NULL_SENTINEL: Final = ""
SNOWFLAKE_TO_DUCKDB: Final[dict[str, str]] = {
    "ARRAY": "JSON",
    "BINARY": "BLOB",
    "BOOLEAN": "BOOLEAN",
    "DATE": "DATE",
    "DECIMAL": "DECIMAL(38,0)",
    "FLOAT": "DOUBLE",
    "INTEGER": "BIGINT",
    "GEOGRAPHY": "VARCHAR",
    "NUMBER": "DECIMAL(38,0)",
    "OBJECT": "JSON",
    "TEXT": "VARCHAR",
    "TIME": "TIME",
    "TIMESTAMP_LTZ": "TIMESTAMPTZ",
    "TIMESTAMP_NTZ": "TIMESTAMP",
    "TIMESTAMP_TZ": "TIMESTAMPTZ",
    "VARCHAR": "VARCHAR",
    "VARIANT": "JSON",
}


class FixtureError(ValueError):
    """Raised when a fixture set cannot be loaded deterministically."""

    @classmethod
    def missing_schema(cls, root: Path) -> FixtureError:
        """Create an error for a fixture directory without a schema file."""
        return cls(f"{root}: missing {SCHEMA_FILE}")

    @classmethod
    def missing_csv(cls, table: str, path: Path) -> FixtureError:
        """Create an error for a declared table with no CSV data."""
        return cls(f"table {table!r} declares no data file at {path}")

    @classmethod
    def unknown_type(cls, table: str, column: str, type_name: str) -> FixtureError:
        """Create an error for a warehouse type with no DuckDB equivalent."""
        supported = ", ".join(sorted(SNOWFLAKE_TO_DUCKDB))
        return cls(
            f"{table}.{column}: unsupported type {type_name!r}; supported: {supported}"
        )

    @classmethod
    def header_mismatch(
        cls,
        table: str,
        declared: Sequence[str],
        found: Sequence[str],
    ) -> FixtureError:
        """Create an error for a CSV header that does not match the schema."""
        return cls(
            f"table {table!r} CSV header {list(found)} does not match declared "
            f"columns {list(declared)}"
        )


@dataclass(frozen=True, slots=True)
class FixtureColumn:
    """One declared column, in warehouse type vocabulary."""

    name: str
    type_name: str

    def duckdb_type(self, table: str) -> str:
        """Return the DuckDB type for this column, or fail fast."""
        normalized = self.type_name.strip().upper()
        if normalized.startswith(("NUMBER(", "DECIMAL(", "NUMERIC(")):
            return "DECIMAL" + normalized[normalized.index("(") :]
        if normalized.startswith("VARCHAR("):
            return "VARCHAR"
        mapped = SNOWFLAKE_TO_DUCKDB.get(normalized)
        if mapped is None:
            raise FixtureError.unknown_type(table, self.name, self.type_name)
        return mapped


@dataclass(frozen=True, slots=True)
class FixtureTable:
    """One table mirroring a warehouse table, backed by a CSV file."""

    schema: str
    name: str
    columns: tuple[FixtureColumn, ...]
    data_file: Path

    @property
    def qualified_name(self) -> str:
        """Return the schema-qualified table name."""
        return f"{self.schema}.{self.name}"

    def create_statement(self) -> str:
        """Return explicit DDL so no type is ever inferred from the CSV."""
        declared = ",\n    ".join(
            f'"{column.name}" {column.duckdb_type(self.qualified_name)}'
            for column in self.columns
        )
        return f'CREATE TABLE "{self.schema}"."{self.name}" (\n    {declared}\n)'

    def verify_header(self) -> None:
        """Reject a CSV whose header does not match the declared columns."""
        with self.data_file.open(newline="", encoding="utf-8") as handle:
            header = next(csv.reader(handle), [])
        declared = [column.name for column in self.columns]
        if list(header) != declared:
            raise FixtureError.header_mismatch(self.qualified_name, declared, header)


@dataclass(frozen=True, slots=True)
class FixtureSet:
    """Every table one sandbox environment exposes, plus its content digest."""

    root: Path
    tables: tuple[FixtureTable, ...]

    @property
    def schemas(self) -> tuple[str, ...]:
        """Return the distinct schema names in declaration order."""
        seen: list[str] = []
        for table in self.tables:
            if table.schema not in seen:
                seen.append(table.schema)
        return tuple(seen)

    def digest(self) -> str:
        """Return a content digest over the schema and every CSV file."""
        hasher = hashlib.sha256()
        for table in sorted(self.tables, key=lambda item: item.qualified_name):
            hasher.update(table.qualified_name.encode("utf-8"))
            hasher.update(table.create_statement().encode("utf-8"))
            hasher.update(table.data_file.read_bytes())
        return hasher.hexdigest()


def load_fixture_set(root: Path) -> FixtureSet:
    """Read a fixture directory's schema declaration and locate its CSV data."""
    schema_path = root / SCHEMA_FILE
    if not schema_path.is_file():
        raise FixtureError.missing_schema(root)
    raw = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        message = f"{schema_path}: schema must be a mapping"
        raise FixtureError(message)
    declared = raw.get("tables")
    if not isinstance(declared, list) or not declared:
        message = f"{schema_path}: tables must be a non-empty list"
        raise FixtureError(message)
    return FixtureSet(root=root, tables=tuple(_load_tables(root, declared)))


def _load_tables(root: Path, declared: Iterable[object]) -> Iterable[FixtureTable]:
    for entry in declared:
        if not isinstance(entry, dict):
            message = f"{root}: each table must be a mapping"
            raise FixtureError(message)
        schema = str(entry["schema"])
        name = str(entry["name"])
        columns = tuple(
            FixtureColumn(name=str(column["name"]), type_name=str(column["type"]))
            for column in entry["columns"]
        )
        data_file = root / str(entry.get("data", f"{schema}.{name}.csv"))
        if not data_file.is_file():
            raise FixtureError.missing_csv(f"{schema}.{name}", data_file)
        table = FixtureTable(
            schema=schema,
            name=name,
            columns=columns,
            data_file=data_file,
        )
        table.verify_header()
        yield table
