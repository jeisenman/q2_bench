from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from workspaces.data_engineering.workflows.lineage import (
    DatasetField,
    EdgeKind,
    JobAllocation,
    LineageEdge,
    LineageGraph,
    LineageNode,
    LineageQueryError,
    LineageQueryService,
    RepositoryManifest,
    ResourceAllocation,
    SourceLocation,
    Transformation,
    TraversalDirection,
    airflow_job_identifier,
    dataset_identifier,
)

REPOSITORY = "precisionlender/di-pipelines"
PROFILE = "maximum-permissions"


class GraphSource:
    def __init__(self, graphs: tuple[LineageGraph, ...]) -> None:
        self.graphs = graphs

    def latest(self, repository: str, profile: str) -> LineageGraph | None:
        if repository != REPOSITORY or profile != PROFILE or not self.graphs:
            return None
        return self.graphs[0]

    def history(
        self,
        repository: str,
        profile: str,
        limit: int,
    ) -> tuple[LineageGraph, ...]:
        if repository != REPOSITORY or profile != PROFILE:
            return ()
        return self.graphs[:limit]


def manifest(revision: int) -> RepositoryManifest:
    return RepositoryManifest(
        graph_id=UUID(f"00000000-0000-0000-0000-{revision:012d}"),
        repository=REPOSITORY,
        commit_sha=str(revision) * 40,
        source_ref="master",
        profile=PROFILE,
        extractor_version="2",
        generated_at=datetime(2026, 10, revision, tzinfo=UTC),
    )


def graph(revision: int, nodes: tuple[LineageNode, ...]) -> LineageGraph:
    source, job, output = nodes[:3]
    return LineageGraph(
        manifest(revision),
        nodes,
        (
            LineageEdge(source.node_id, job.node_id, EdgeKind.CONSUMES),
            LineageEdge(job.node_id, output.node_id, EdgeKind.PRODUCES),
        ),
    )


def nodes(description: str = "Engagement output") -> tuple[LineageNode, ...]:
    source = LineageNode(
        dataset_identifier("Primary", "PL/Chats"),
        fields=(DatasetField("engagement_id", "string"),),
    )
    job = LineageNode(airflow_job_identifier("main", "aggregate_engagements"))
    output = LineageNode(
        dataset_identifier("Primary", "PL/CatEngagements"),
        description=description,
        fields=(DatasetField("category_name", "string"),),
        transformations=(
            Transformation(
                name="aggregate_pl_cat_engagements",
                implementation="AggregateJob",
                compute="spark",
                source=SourceLocation("dags/task_groups/engagements.py", 42),
                allocation=JobAllocation(
                    standard=ResourceAllocation(
                        "spark",
                        spark_variables=(("executor_instances", "4"),),
                    )
                ),
            ),
        ),
    )
    return source, job, output


def test_search_and_transformation_details_include_graph_revision() -> None:
    expected = graph(3, nodes())
    service = LineageQueryService(GraphSource((expected,)))

    search = service.search_datasets("category_name")
    details = service.transformation_details(search.nodes[0].node_id)

    assert search.manifest == expected.manifest
    assert [node.identifier.name for node in search.nodes] == [
        "primary/pl/catengagements"
    ]
    assert details.manifest == expected.manifest
    assert details.node.transformations[0].allocation is not None


def test_traversal_follows_upstream_and_downstream_edges() -> None:
    expected = graph(3, nodes())
    service = LineageQueryService(GraphSource((expected,)))
    source, job, output = expected.nodes

    downstream = service.traverse(
        source.node_id,
        TraversalDirection.DOWNSTREAM,
        depth=2,
    )
    upstream = service.traverse(
        output.node_id,
        TraversalDirection.UPSTREAM,
        depth=2,
    )

    assert {node.node_id for node in downstream.nodes} == {
        job.node_id,
        output.node_id,
    }
    assert {node.node_id for node in upstream.nodes} == {
        source.node_id,
        job.node_id,
    }
    assert not downstream.truncated


def test_traversal_reports_limits_and_invalid_queries() -> None:
    expected = graph(3, nodes())
    service = LineageQueryService(GraphSource((expected,)))

    limited = service.traverse(
        expected.nodes[0].node_id,
        TraversalDirection.DOWNSTREAM,
        depth=2,
        limit=1,
    )

    assert limited.truncated
    with pytest.raises(LineageQueryError, match="does not exist"):
        service.transformation_details("dataset:missing/node")
    with pytest.raises(LineageQueryError, match="between 1 and 10"):
        service.traverse(
            expected.nodes[0].node_id,
            TraversalDirection.DOWNSTREAM,
            depth=11,
        )
    with pytest.raises(LineageQueryError, match="no lineage graph"):
        LineageQueryService(GraphSource(())).search_datasets("engagement")


def test_change_history_reports_changed_created_and_removed_nodes() -> None:
    newest_nodes = nodes("Changed description")
    prior_nodes = nodes()
    removed = LineageNode(dataset_identifier("Primary", "Removed"))
    newest = graph(3, newest_nodes)
    prior = graph(2, (*prior_nodes, removed))
    oldest = graph(1, (prior_nodes[0], prior_nodes[1], removed))
    service = LineageQueryService(GraphSource((newest, prior, oldest)))

    current_history = service.change_history(newest_nodes[2].node_id)
    removed_history = service.change_history(removed.node_id)

    assert [item.change_type for item in current_history] == ["changed", "created"]
    assert [item.change_type for item in removed_history] == ["removed", "created"]
    assert removed_history[0].node is None


def test_search_ranks_exact_names_and_validates_bounds() -> None:
    base = nodes()
    exact = replace(
        base[0],
        identifier=dataset_identifier("Primary", "Chats"),
    )
    expected = graph(3, (exact, base[1], base[2]))
    service = LineageQueryService(GraphSource((expected,)))

    result = service.search_datasets("primary/chats", limit=1)

    assert result.nodes == (exact,)
    with pytest.raises(LineageQueryError, match="must not be empty"):
        service.search_datasets(" ")
    with pytest.raises(LineageQueryError, match="between 1 and 100"):
        service.search_datasets("chats", limit=101)
