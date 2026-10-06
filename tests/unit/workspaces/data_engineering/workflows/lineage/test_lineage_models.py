from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from workspaces.data_engineering.workflows.lineage import (
    CanonicalIdentifier,
    ClientAllocationOverride,
    DatasetField,
    DatasetLocation,
    DerivedContext,
    EdgeKind,
    JobAllocation,
    LineageEdge,
    LineageGraph,
    LineageNode,
    NodeEnrichment,
    NodeKind,
    RepositoryManifest,
    RepositoryRevision,
    ResourceAllocation,
    SourceLocation,
    Transformation,
    airflow_job_identifier,
    dataset_identifier,
    diff_graphs,
    snowflake_dataset_identifier,
)
from workspaces.data_engineering.workflows.lineage.errors import (
    LineageValidationError,
)
from workspaces.data_engineering.workflows.lineage.identifiers import (
    canonical_segment,
)

GRAPH_ID = UUID("11111111-1111-1111-1111-111111111111")
PREVIOUS_ID = UUID("22222222-2222-2222-2222-222222222222")


def manifest(graph_id: UUID = GRAPH_ID) -> RepositoryManifest:
    return RepositoryManifest(
        graph_id=graph_id,
        repository="precisionlender/di-pipelines",
        commit_sha="a" * 40,
        source_ref="master",
        profile="maximum-permissions",
        extractor_version="1",
        generated_at=datetime(2026, 10, 5, tzinfo=UTC),
        source_repositories=(
            RepositoryRevision(
                "precisionlender/di-pipelines",
                "a" * 40,
                "master",
            ),
        ),
    )


def node(
    identifier: CanonicalIdentifier,
    *,
    description: str = "description",
) -> LineageNode:
    return LineageNode(
        identifier=identifier,
        description=description,
        version="v1.0",
        fields=(DatasetField("id", "StringType()", False, "identifier", True),),
        locations=(DatasetLocation("InternalADLS", "client/{id}"),),
        transformations=(
            Transformation(
                "aggregate",
                "AggregateJob",
                "large",
                SourceLocation("task_groups/sample.py", 10),
                JobAllocation(
                    standard=ResourceAllocation(
                        compute="batch",
                        spark_variables=(("executor_memory", "16g"),),
                    ),
                    larger_clients=(
                        ClientAllocationOverride(
                            client_id="11111111-1111-4111-8111-111111111111",
                            client_name="Bigger Bank",
                            resource_size="large",
                            allocation=ResourceAllocation(
                                compute="k8s_pod",
                                container_resources=(("limits.memory", "16Gi"),),
                            ),
                        ),
                    ),
                ),
            ),
        ),
        sources=(SourceLocation("metadata/sample.py", 2),),
        owners=("data-engineering",),
        context=DerivedContext("Materialized by one task.", "test"),
        attributes=(("stage", "Primary"),),
        enrichments=(
            NodeEnrichment(
                "engine-calculation",
                "CalculateRelationship",
                "Public engine calculation contract.",
                (SourceLocation("engine/IRARelationshipEngineService.cs", 10),),
            ),
        ),
    )


def test_identifiers_normalize_source_names() -> None:
    dataset = dataset_identifier("Primary", "PL Andi/Chat-Events")
    job = airflow_job_identifier("L3 Main Graph", "Aggregate Chats")
    table = snowflake_dataset_identifier("Client DM", "Chat Events")

    assert canonical_segment(" A/B ") == "a_b"
    assert dataset.name == "primary/pl_andi/chat_events"
    assert job.value.endswith("/l3_main_graph/aggregate_chats")
    assert table.name == "client_dm.chat_events"

    with pytest.raises(LineageValidationError, match="no usable"):
        canonical_segment("---")
    with pytest.raises(LineageValidationError, match="at least one"):
        dataset_identifier("Primary", "")
    with pytest.raises(LineageValidationError, match="namespace"):
        CanonicalIdentifier(NodeKind.DATASET, " ", "name")
    with pytest.raises(LineageValidationError, match="name"):
        CanonicalIdentifier(NodeKind.DATASET, "namespace", " ")


def test_graph_round_trip_preserves_all_entity_content() -> None:
    dataset = node(dataset_identifier("Primary", "PL/Chats"))
    job = node(airflow_job_identifier("main", "aggregate"))
    edge = LineageEdge(job.node_id, dataset.node_id, EdgeKind.PRODUCES)
    graph = LineageGraph(manifest(), (dataset, job), (edge,))

    restored = LineageGraph.from_dict(graph.to_dict())

    assert restored == graph
    assert restored.fingerprint == graph.fingerprint
    assert graph.to_json().endswith("\n")
    assert graph.to_dict()["format"] == "q2-openlineage-graph/v1"
    assert dataset.content_hash == restored.nodes[0].content_hash


def test_graph_validation_rejects_invalid_manifests_nodes_and_edges() -> None:
    with pytest.raises(LineageValidationError, match="40"):
        replace(manifest(), commit_sha="short")
    with pytest.raises(LineageValidationError, match="timezone"):
        replace(manifest(), generated_at=datetime(2026, 10, 5))
    with pytest.raises(LineageValidationError, match="endpoints"):
        LineageEdge("", "target", EdgeKind.CONSUMES)

    dataset = node(dataset_identifier("Primary", "PL/Chats"))
    with pytest.raises(LineageValidationError, match="duplicate"):
        LineageGraph(manifest(), (dataset, dataset), ())
    with pytest.raises(LineageValidationError, match="missing nodes"):
        LineageGraph(
            manifest(),
            (dataset,),
            (
                LineageEdge(
                    dataset.node_id,
                    "job:q2://missing/job",
                    EdgeKind.CONSUMES,
                ),
            ),
        )


def test_diff_reports_content_changes_and_downstream_impact() -> None:
    source_id = dataset_identifier("Primary", "PL/Source")
    job_id = airflow_job_identifier("main", "consumer")
    output_id = dataset_identifier("Primary", "PL/Output")
    source = node(source_id)
    job = node(job_id)
    output = node(output_id)
    edges = (
        LineageEdge(source.node_id, job.node_id, EdgeKind.CONSUMES),
        LineageEdge(job.node_id, output.node_id, EdgeKind.PRODUCES),
    )
    previous = LineageGraph(manifest(PREVIOUS_ID), (source, job, output), edges)
    changed_source = node(source_id, description="new schema")
    added = node(dataset_identifier("Primary", "PL/Added"))
    current = LineageGraph(
        manifest(),
        (changed_source, job, output, added),
        (*edges, LineageEdge(output.node_id, added.node_id, EdgeKind.CONSUMES)),
    )

    result = diff_graphs(previous, current)

    assert result.changed
    assert result.changed_nodes == (source.node_id,)
    assert result.added_nodes == (added.node_id,)
    assert job.node_id in result.impacted_nodes
    assert output.node_id in result.impacted_nodes
    assert added.node_id not in result.impacted_nodes
    assert diff_graphs(None, current).previous_graph_id is None
