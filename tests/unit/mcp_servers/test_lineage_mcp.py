from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest

from mcp_servers import lineage as lineage_mcp
from workspaces.data_engineering.workflows.lineage import (
    RADAR_LINEAGE_REPOSITORY,
    EdgeKind,
    JobAllocation,
    LineageEdge,
    LineageGraph,
    LineageNode,
    NodeEnrichment,
    RepositoryManifest,
    ResourceAllocation,
    SourceLocation,
    Transformation,
    airflow_job_identifier,
    dataset_identifier,
)


class GraphSource:
    def __init__(self, graph: LineageGraph) -> None:
        self.graph = graph
        self.requested_repositories: list[str] = []

    def latest(self, repository: str, _profile: str) -> LineageGraph:
        self.requested_repositories.append(repository)
        return self.graph

    def history(
        self,
        _repository: str,
        _profile: str,
        _limit: int,
    ) -> tuple[LineageGraph, ...]:
        return (self.graph,)


def graph() -> LineageGraph:
    source = LineageNode(dataset_identifier("Primary", "PL/Chats"))
    job = LineageNode(airflow_job_identifier("main", "aggregate"))
    output = LineageNode(
        dataset_identifier("Primary", "PL/CatEngagements"),
        description="Categorized client engagements",
        transformations=(
            Transformation(
                "aggregate_pl_cat_engagements",
                "AggregateJob",
                "spark",
                SourceLocation("dags/task_groups/engagements.py", 42),
                JobAllocation(
                    standard=ResourceAllocation(
                        "spark",
                        spark_variables=(("executor_instances", "4"),),
                    )
                ),
            ),
        ),
        enrichments=(
            NodeEnrichment(
                "engine-calculation",
                "CalculateRelationship",
                "Engine calculation contract.",
                (SourceLocation("engine/IRelationship.cs", 10),),
            ),
        ),
    )
    return LineageGraph(
        RepositoryManifest(
            graph_id=UUID("11111111-1111-1111-1111-111111111111"),
            repository="precisionlender/di-pipelines",
            commit_sha="a" * 40,
            source_ref="master",
            profile="maximum-permissions",
            extractor_version="2",
            generated_at=datetime(2026, 10, 5, tzinfo=UTC),
        ),
        (source, job, output),
        (
            LineageEdge(source.node_id, job.node_id, EdgeKind.CONSUMES),
            LineageEdge(job.node_id, output.node_id, EdgeKind.PRODUCES),
        ),
    )


def install_source(
    monkeypatch: pytest.MonkeyPatch,
    expected: LineageGraph,
) -> GraphSource:
    source = GraphSource(expected)
    monkeypatch.setattr(lineage_mcp, "_source", lambda: source)
    return source


def test_lineage_mcp_search_traversal_and_allocations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = graph()
    source = install_source(monkeypatch, expected)
    output = expected.nodes[2]

    search = asyncio.run(lineage_mcp.search_lineage_datasets("engagement"))
    upstream = asyncio.run(lineage_mcp.get_lineage_upstream(output.node_id, depth=2))
    details = asyncio.run(lineage_mcp.get_lineage_transformation(output.node_id))

    assert search["graph"]["commitSha"] == "a" * 40
    assert search["datasets"][0]["id"] == output.node_id
    assert upstream["nodeCount"] == len(expected.nodes) - 1
    transformations = details["node"]["transformations"]
    assert transformations[0]["allocation"]["standard"]["compute"] == "spark"
    assert details["node"]["enrichments"][0]["name"] == "CalculateRelationship"
    assert details["node"]["enrichmentCount"] == 1
    assert source.requested_repositories == [RADAR_LINEAGE_REPOSITORY] * 3


def test_lineage_mcp_history_and_debug_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = graph()
    install_source(monkeypatch, expected)
    monkeypatch.setenv("Q2_MCP_DEBUG", "1")

    result = asyncio.run(
        lineage_mcp.get_lineage_change_history(expected.nodes[2].node_id)
    )

    assert result["revisions"][0]["changeType"] == "created"
    assert result["debug_trace"]["enabled"] is True


def test_lineage_mcp_source_prefers_postgres_when_dsn_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = GraphSource(graph())
    monkeypatch.setenv("LINEAGE_POSTGRES_DSN", "postgresql://lineage")
    monkeypatch.setattr(lineage_mcp, "PostgresLineageStore", lambda _dsn: sentinel)

    assert lineage_mcp._source() is sentinel
    assert lineage_mcp._source_mode() == "postgres"
