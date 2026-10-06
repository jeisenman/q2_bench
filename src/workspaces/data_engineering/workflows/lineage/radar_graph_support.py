"""Small helpers shared by the aggregate RADAR graph builder."""

from __future__ import annotations

from dataclasses import replace

from workspaces.data_engineering.workflows.lineage.graph_models import LineageGraph


def prefix_di_sources(graph: LineageGraph) -> LineageGraph:
    """Disambiguate DI Pipelines source paths in a multi-repository graph."""
    nodes = tuple(
        replace(
            node,
            transformations=tuple(
                replace(
                    item,
                    source=replace(
                        item.source,
                        path=f"di-pipelines/{item.source.path}",
                    ),
                )
                for item in node.transformations
            ),
            sources=tuple(
                replace(source, path=f"di-pipelines/{source.path}")
                for source in node.sources
            ),
        )
        for node in graph.nodes
    )
    return LineageGraph(graph.manifest, nodes, graph.edges)


def stage_description(stage: str) -> str:
    """Return the plain-language contract for one notebook stage."""
    descriptions = {
        "extract": "Extracts client-uploaded files into normalized RawInputs.",
        "mapping": "Maps RawInputs and application history into MappingResults.",
        "transform": "Transforms mapped records into TransformResults.",
    }
    return descriptions[stage]
