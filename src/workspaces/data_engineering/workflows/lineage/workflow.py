"""Orchestrate DI Pipelines extraction, diffing, and persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from workspaces.data_engineering.workflows.lineage.allocations import (
    AllocationIndex,
)
from workspaces.data_engineering.workflows.lineage.builder import (
    DiPipelinesGraphBuilder,
)
from workspaces.data_engineering.workflows.lineage.diff import diff_graphs
from workspaces.data_engineering.workflows.lineage.graph_models import (
    GraphDiff,
    LineageGraph,
)
from workspaces.data_engineering.workflows.lineage.main_graph import (
    MainGraphScanner,
)
from workspaces.data_engineering.workflows.lineage.metadata import MetadataIndex
from workspaces.data_engineering.workflows.lineage.ports import LineageStore
from workspaces.data_engineering.workflows.lineage.radar_graph import (
    RadarGraphBuilder,
)
from workspaces.data_engineering.workflows.lineage.radar_repositories import (
    RadarRepositories,
)
from workspaces.data_engineering.workflows.lineage.repository import (
    radar_manifest,
    repository_manifest,
)
from workspaces.data_engineering.workflows.lineage.source import SourceIndex


@dataclass(frozen=True, slots=True)
class LineageSyncOutcome:
    """Graph, change summary, and persistence result for one synchronization."""

    graph: LineageGraph
    diff: GraphDiff
    inserted: bool


def build_di_pipelines_graph(
    repository: Path,
    *,
    generated_at: datetime | None = None,
    source_ref: str | None = None,
) -> LineageGraph:
    """Build the intended L3 and Snowflake graph for one checkout."""
    manifest = repository_manifest(
        repository,
        generated_at=generated_at,
        source_ref=source_ref,
    )
    source_index = SourceIndex(repository.resolve())
    metadata = MetadataIndex.from_repository(repository.resolve())
    allocations = AllocationIndex.from_repository(source_index)
    intended = MainGraphScanner(source_index).scan()
    return DiPipelinesGraphBuilder(source_index, metadata, allocations).build(
        manifest,
        intended,
    )


def sync_di_pipelines_lineage(
    repository: Path,
    store: LineageStore | None = None,
    *,
    generated_at: datetime | None = None,
    source_ref: str | None = None,
) -> LineageSyncOutcome:
    """Build, compare, and optionally persist one repository graph version."""
    graph = build_di_pipelines_graph(
        repository,
        generated_at=generated_at,
        source_ref=source_ref,
    )
    previous = (
        store.latest(graph.manifest.repository, graph.manifest.profile)
        if store
        else None
    )
    graph_diff = diff_graphs(previous, graph)
    inserted = store.save(graph, graph_diff) if store else False
    return LineageSyncOutcome(graph, graph_diff, inserted)


def build_radar_lineage_graph(
    repositories: RadarRepositories,
    *,
    generated_at: datetime | None = None,
    source_ref: str | None = None,
) -> LineageGraph:
    """Build structural RADAR lineage across all required repositories."""
    di_graph = build_di_pipelines_graph(
        repositories.di_pipelines,
        generated_at=generated_at,
    )
    source_index = SourceIndex(repositories.di_pipelines.resolve())
    intended = MainGraphScanner(source_index).scan()
    manifest = radar_manifest(
        repositories.as_mapping(),
        generated_at=generated_at,
        source_ref=source_ref,
    )
    return RadarGraphBuilder(repositories).build(manifest, di_graph, intended)


def sync_radar_lineage(
    repositories: RadarRepositories,
    store: LineageStore | None = None,
    *,
    generated_at: datetime | None = None,
    source_ref: str | None = None,
) -> LineageSyncOutcome:
    """Build, compare, and optionally persist aggregate RADAR lineage."""
    graph = build_radar_lineage_graph(
        repositories,
        generated_at=generated_at,
        source_ref=source_ref,
    )
    previous = (
        store.latest(graph.manifest.repository, graph.manifest.profile)
        if store
        else None
    )
    graph_diff = diff_graphs(previous, graph)
    inserted = store.save(graph, graph_diff) if store else False
    return LineageSyncOutcome(graph, graph_diff, inserted)
