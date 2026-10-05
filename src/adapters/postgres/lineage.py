"""Persist versioned repository lineage graphs in PostgreSQL."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from adapters.postgres.errors import (
    PostgresLineageConfigurationError,
    PostgresLineageError,
)
from workspaces.data_engineering.workflows.lineage.graph_models import (
    GraphDiff,
    LineageGraph,
)

LINEAGE_POSTGRES_DSN_ENV = "LINEAGE_POSTGRES_DSN"


class PostgresLineageStore:
    """Store immutable graph versions and normalized searchable entities."""

    def __init__(self, dsn: str) -> None:
        """Initialize the adapter with an explicit PostgreSQL DSN."""
        if not dsn.strip():
            message = "lineage PostgreSQL DSN must not be empty"
            raise ValueError(message)
        self._dsn = dsn

    @classmethod
    def from_environment(cls) -> PostgresLineageStore:
        """Build the adapter from the required lineage DSN environment value."""
        dsn = os.environ.get(LINEAGE_POSTGRES_DSN_ENV)
        if not dsn:
            message = (
                f"{LINEAGE_POSTGRES_DSN_ENV} is required to persist lineage graphs"
            )
            raise PostgresLineageConfigurationError(message)
        return cls(dsn)

    def latest(self, repository: str, profile: str) -> LineageGraph | None:
        """Return the latest stored graph for a repository and profile."""
        query = """
            SELECT graph
            FROM lineage.graphs
            WHERE repository = %s AND profile = %s
            ORDER BY generated_at DESC, created_at DESC
            LIMIT 1
        """
        try:
            with (
                psycopg.connect(self._dsn) as connection,
                connection.cursor(row_factory=dict_row) as cursor,
            ):
                cursor.execute(query, (repository, profile))
                row = cursor.fetchone()
        except psycopg.Error as error:
            message = f"unable to query repository lineage: {error}"
            raise PostgresLineageError(message) from error
        if row is None:
            return None
        return LineageGraph.from_dict(_graph_mapping(row["graph"]))

    def history(
        self,
        repository: str,
        profile: str,
        limit: int,
    ) -> tuple[LineageGraph, ...]:
        """Return stored graph versions newest first."""
        if limit < 1:
            message = "lineage history limit must be at least 1"
            raise ValueError(message)
        query = """
            SELECT graph
            FROM lineage.graphs
            WHERE repository = %s AND profile = %s
            ORDER BY generated_at DESC, created_at DESC
            LIMIT %s
        """
        try:
            with (
                psycopg.connect(self._dsn) as connection,
                connection.cursor(row_factory=dict_row) as cursor,
            ):
                cursor.execute(query, (repository, profile, limit))
                rows = cursor.fetchall()
        except psycopg.Error as error:
            message = f"unable to query repository lineage history: {error}"
            raise PostgresLineageError(message) from error
        return tuple(
            LineageGraph.from_dict(_graph_mapping(row["graph"])) for row in rows
        )

    def save(self, graph: LineageGraph, diff: GraphDiff) -> bool:
        """Atomically persist a graph and its normalized entity rows."""
        try:
            with (
                psycopg.connect(self._dsn) as connection,
                connection.cursor(row_factory=dict_row) as cursor,
            ):
                cursor.execute(
                    _INSERT_GRAPH,
                    (
                        graph.manifest.graph_id,
                        graph.manifest.repository,
                        graph.manifest.commit_sha,
                        graph.manifest.source_ref,
                        graph.manifest.profile,
                        graph.manifest.extractor_version,
                        graph.manifest.generated_at,
                        graph.fingerprint,
                        Jsonb(graph.to_dict()),
                    ),
                )
                if cursor.fetchone() is None:
                    return False
                cursor.executemany(
                    _INSERT_NODE,
                    (
                        (
                            graph.manifest.graph_id,
                            node.node_id,
                            node.identifier.kind.value,
                            node.identifier.namespace,
                            node.identifier.name,
                            node.content_hash,
                            Jsonb(node.to_dict()),
                        )
                        for node in graph.nodes
                    ),
                )
                cursor.executemany(
                    _INSERT_EDGE,
                    (
                        (
                            graph.manifest.graph_id,
                            edge.edge_id,
                            edge.source_id,
                            edge.target_id,
                            edge.kind.value,
                            edge.content_hash,
                            Jsonb(edge.to_dict()),
                        )
                        for edge in graph.edges
                    ),
                )
                cursor.execute(
                    _INSERT_DIFF,
                    (
                        graph.manifest.graph_id,
                        diff.previous_graph_id,
                        diff.changed,
                        Jsonb(diff.to_dict()),
                    ),
                )
        except psycopg.Error as error:
            message = f"unable to persist repository lineage: {error}"
            raise PostgresLineageError(message) from error
        return True


def _graph_mapping(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, Mapping):
        message = "stored lineage graph is not a JSON object"
        raise PostgresLineageError(message)
    return {str(key): item for key, item in value.items()}


_INSERT_GRAPH = """
    INSERT INTO lineage.graphs (
        graph_id, repository, commit_sha, source_ref, profile,
        extractor_version, generated_at, fingerprint, graph
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (repository, commit_sha, profile, extractor_version) DO NOTHING
    RETURNING graph_id
"""

_INSERT_NODE = """
    INSERT INTO lineage.nodes (
        graph_id, node_id, kind, namespace, name, content_hash, payload
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s)
"""

_INSERT_EDGE = """
    INSERT INTO lineage.edges (
        graph_id, edge_id, source_node_id, target_node_id,
        kind, content_hash, payload
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s)
"""

_INSERT_DIFF = """
    INSERT INTO lineage.graph_diffs (
        graph_id, previous_graph_id, changed, summary
    )
    VALUES (%s, %s, %s, %s)
"""
