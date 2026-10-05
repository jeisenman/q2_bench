from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from psycopg import OperationalError

from adapters.postgres import (
    LINEAGE_POSTGRES_DSN_ENV,
    PostgresLineageConfigurationError,
    PostgresLineageError,
    PostgresLineageStore,
)
from adapters.postgres import lineage as lineage_module
from workspaces.data_engineering.workflows.lineage import (
    EdgeKind,
    GraphDiff,
    LineageEdge,
    LineageGraph,
    LineageNode,
    RepositoryManifest,
    airflow_job_identifier,
    dataset_identifier,
)

ROOT = Path(__file__).parents[4]
MIGRATION = ROOT / "migrations/postgres/002_lineage.sql"
GRAPH_ID = UUID("11111111-1111-1111-1111-111111111111")
PROVIDER_ERROR = OperationalError("database unavailable")


def graph() -> LineageGraph:
    dataset = LineageNode(dataset_identifier("Primary", "PL/Chats"))
    job = LineageNode(airflow_job_identifier("main", "aggregate"))
    return LineageGraph(
        RepositoryManifest(
            graph_id=GRAPH_ID,
            repository="precisionlender/di-pipelines",
            commit_sha="a" * 40,
            source_ref="master",
            profile="maximum-permissions",
            extractor_version="1",
            generated_at=datetime(2026, 10, 5, tzinfo=UTC),
        ),
        (dataset, job),
        (LineageEdge(job.node_id, dataset.node_id, EdgeKind.PRODUCES),),
    )


class FakeCursor:
    def __init__(
        self,
        *,
        stored_graph: object | None = None,
        stored_graphs: list[object] | None = None,
        insert_graph: bool = True,
    ) -> None:
        self.stored_graph = stored_graph
        self.stored_graphs = stored_graphs or []
        self.insert_graph = insert_graph
        self.statements: list[str] = []
        self.batches: list[list[tuple[object, ...]]] = []
        self._row: dict[str, Any] | None = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query, _parameters=None) -> None:
        statement = str(query)
        self.statements.append(statement)
        if "SELECT graph" in statement:
            self._row = (
                {"graph": self.stored_graph} if self.stored_graph is not None else None
            )
        elif "RETURNING graph_id" in statement:
            self._row = {"graph_id": GRAPH_ID} if self.insert_graph else None
        else:
            self._row = None

    def executemany(self, query, parameters) -> None:
        self.statements.append(str(query))
        self.batches.append(list(parameters))

    def fetchone(self):
        return self._row

    def fetchall(self):
        return [{"graph": item} for item in self.stored_graphs]


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cursor(self, **_kwargs):
        return self._cursor


def install_connection(
    monkeypatch: pytest.MonkeyPatch,
    cursor: FakeCursor,
) -> None:
    monkeypatch.setattr(
        lineage_module.psycopg,
        "connect",
        lambda _dsn: FakeConnection(cursor),
    )


def test_lineage_migration_defines_normalized_versioned_graph_schema() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE SCHEMA IF NOT EXISTS lineage" in sql
    assert "UNIQUE (repository, commit_sha, profile, extractor_version)" in sql
    assert "CREATE TABLE IF NOT EXISTS lineage.nodes" in sql
    assert "CREATE TABLE IF NOT EXISTS lineage.edges" in sql
    assert "CREATE TABLE IF NOT EXISTS lineage.graph_diffs" in sql
    assert "FOREIGN KEY (graph_id, source_node_id)" in sql
    assert "lineage_edge_downstream" in sql


def test_postgres_lineage_configuration_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        PostgresLineageStore(" ")
    monkeypatch.delenv(LINEAGE_POSTGRES_DSN_ENV, raising=False)
    with pytest.raises(
        PostgresLineageConfigurationError,
        match=LINEAGE_POSTGRES_DSN_ENV,
    ):
        PostgresLineageStore.from_environment()
    monkeypatch.setenv(LINEAGE_POSTGRES_DSN_ENV, "postgresql://lineage")
    assert isinstance(PostgresLineageStore.from_environment(), PostgresLineageStore)


def test_postgres_store_reads_graph_dict_and_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = graph()
    cursor = FakeCursor(stored_graph=expected.to_dict())
    install_connection(monkeypatch, cursor)
    store = PostgresLineageStore("postgresql://lineage")

    assert store.latest(expected.manifest.repository, expected.manifest.profile) == (
        expected
    )

    cursor = FakeCursor(stored_graph=json.dumps(expected.to_dict()))
    install_connection(monkeypatch, cursor)
    assert store.latest("repository", "profile") == expected

    cursor = FakeCursor()
    install_connection(monkeypatch, cursor)
    assert store.latest("repository", "profile") is None


def test_postgres_store_reads_bounded_graph_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = graph()
    cursor = FakeCursor(
        stored_graphs=[expected.to_dict(), json.dumps(expected.to_dict())]
    )
    install_connection(monkeypatch, cursor)
    store = PostgresLineageStore("postgresql://lineage")

    assert store.history("repository", "profile", 2) == (expected, expected)
    with pytest.raises(ValueError, match="at least 1"):
        store.history("repository", "profile", 0)


def test_postgres_store_inserts_graph_nodes_edges_and_diff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = graph()
    cursor = FakeCursor()
    install_connection(monkeypatch, cursor)
    store = PostgresLineageStore("postgresql://lineage")

    inserted = store.save(expected, GraphDiff(None, added_nodes=("node",)))

    assert inserted
    assert len(cursor.batches[0]) == len(expected.nodes)
    assert len(cursor.batches[1]) == len(expected.edges)
    assert any("INSERT INTO lineage.graph_diffs" in item for item in cursor.statements)

    conflict = FakeCursor(insert_graph=False)
    install_connection(monkeypatch, conflict)
    assert not store.save(expected, GraphDiff(GRAPH_ID))
    assert conflict.batches == []


def test_postgres_store_wraps_provider_and_invalid_payload_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        lineage_module.psycopg,
        "connect",
        lambda _dsn: (_ for _ in ()).throw(PROVIDER_ERROR),
    )
    store = PostgresLineageStore("postgresql://lineage")
    with pytest.raises(PostgresLineageError, match="query"):
        store.latest("repository", "profile")
    with pytest.raises(PostgresLineageError, match="history"):
        store.history("repository", "profile", 2)
    with pytest.raises(PostgresLineageError, match="persist"):
        store.save(graph(), GraphDiff(None))

    cursor = FakeCursor(stored_graph=["not", "mapping"])
    install_connection(monkeypatch, cursor)
    with pytest.raises(PostgresLineageError, match="JSON object"):
        store.latest("repository", "profile")
