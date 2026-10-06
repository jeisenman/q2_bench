from __future__ import annotations

from datetime import UTC, datetime

from workspaces.data_engineering.workflows.lineage import (
    EdgeKind,
    RadarRepositories,
    airflow_job_identifier,
    build_radar_lineage_graph,
    radar_job_identifier,
    run_file_identifier,
)

SOURCE_REPOSITORY_COUNT = 6


def test_radar_lineage_builds_structural_file_chain(
    radar_repositories: RadarRepositories,
) -> None:
    graph = build_radar_lineage_graph(
        radar_repositories,
        generated_at=datetime(2026, 10, 5, tzinfo=UTC),
        source_ref="static-analysis",
    )
    edges = {(edge.source_id, edge.target_id, edge.kind) for edge in graph.edges}
    extract = radar_job_identifier("radar-notebooks", "extract").value
    mapping = radar_job_identifier("radar-notebooks", "mapping").value
    transform = radar_job_identifier("radar-notebooks", "transform").value
    dto = radar_job_identifier("pl-dataingress", "engine-dto-mapping").value
    engine = radar_job_identifier(
        "pl-calculation-engine",
        "relationship-family-calculation",
    ).value
    database_output = radar_job_identifier(
        "pl-dataingress",
        "database-output",
    ).value
    upload = run_file_identifier("ClientUploadedFiles").value
    raw = run_file_identifier("RawInputs/RawInputs_Relationships.csv").value
    mapped = run_file_identifier("MappingResults/MappedRelationships.csv").value
    transformed = run_file_identifier(
        "TransformResults/TransformedRelationships.csv"
    ).value
    engine_dto = run_file_identifier("EngineDTO/RelationshipFamilies").value
    engine_result = run_file_identifier(
        "EngineResults/CalculatedRelationships.csv"
    ).value
    db_output = run_file_identifier("DatabaseOutput/dbStagingRelationshipNew.csv").value
    raw_node = next(node for node in graph.nodes if node.node_id == raw)

    assert graph.manifest.repository == "precisionlender/radar-lineage"
    assert graph.manifest.source_ref == "static-analysis"
    assert len(graph.manifest.source_repositories) == SOURCE_REPOSITORY_COUNT
    assert (upload, extract, EdgeKind.CONSUMES) in edges
    assert (extract, raw, EdgeKind.PRODUCES) in edges
    assert (raw, mapping, EdgeKind.CONSUMES) in edges
    assert (mapping, mapped, EdgeKind.PRODUCES) in edges
    assert (mapped, transform, EdgeKind.CONSUMES) in edges
    assert (transform, transformed, EdgeKind.PRODUCES) in edges
    assert (transformed, dto, EdgeKind.CONSUMES) in edges
    assert (dto, engine_dto, EdgeKind.PRODUCES) in edges
    assert (engine_dto, engine, EdgeKind.CONSUMES) in edges
    assert (engine, engine_result, EdgeKind.PRODUCES) in edges
    assert (engine_result, database_output, EdgeKind.CONSUMES) in edges
    assert (database_output, db_output, EdgeKind.PRODUCES) in edges
    assert {
        (source.path, source.line)
        for source in raw_node.sources
        if source.path.startswith("radar-libraries/")
    } == {
        ("radar-libraries/radar_libraries/fileio/loader.py", 1),
        ("radar-libraries/radar_libraries/fileio/outputter.py", 1),
    }


def test_engine_calculations_are_enrichment_only_and_dboutput_links_to_di(
    radar_repositories: RadarRepositories,
) -> None:
    graph = build_radar_lineage_graph(radar_repositories)
    engine_id = radar_job_identifier(
        "pl-calculation-engine",
        "relationship-family-calculation",
    ).value
    engine = next(node for node in graph.nodes if node.node_id == engine_id)
    db_output = run_file_identifier("DatabaseOutput/dbStagingRelationshipNew.csv").value
    di_job = airflow_job_identifier("l3_main_graph", "copies").value

    assert [item.name for item in engine.enrichments] == [
        "IRARelationshipEngineService.CalculateRelationship"
    ]
    assert all(
        dict(item.attributes)["representation"] == "enrichment-only"
        for item in engine.enrichments
    )
    assert not any(
        "CalculateRelationship" in node.identifier.name for node in graph.nodes
    )
    assert any(
        edge.source_id == db_output
        and edge.target_id == di_job
        and edge.kind is EdgeKind.CONSUMES
        and dict(edge.attributes)["evidence"] == "di_pipelines_raFile"
        for edge in graph.edges
    )
    assert all(
        source.path.startswith("di-pipelines/")
        for node in graph.nodes
        if node.identifier.namespace.endswith("/airflow")
        for source in node.sources
    )


def test_radar_manifest_is_deterministic_for_component_revisions(
    radar_repositories: RadarRepositories,
) -> None:
    generated_at = datetime(2026, 10, 5, tzinfo=UTC)
    first = build_radar_lineage_graph(
        radar_repositories,
        generated_at=generated_at,
    )
    second = build_radar_lineage_graph(
        radar_repositories,
        generated_at=generated_at,
    )

    assert first.manifest == second.manifest
    assert first.fingerprint == second.fingerprint
