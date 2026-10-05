"""Deterministic lineage graph comparison and downstream impact analysis."""

from __future__ import annotations

from collections import defaultdict, deque

from workspaces.data_engineering.workflows.lineage.graph_models import (
    GraphDiff,
    LineageGraph,
)


def diff_graphs(
    previous: LineageGraph | None,
    current: LineageGraph,
) -> GraphDiff:
    """Compare two graph versions and identify downstream impact."""
    if previous is None:
        return GraphDiff(
            previous_graph_id=None,
            added_nodes=tuple(node.node_id for node in current.nodes),
            added_edges=tuple(edge.edge_id for edge in current.edges),
        )

    previous_nodes = {node.node_id: node for node in previous.nodes}
    current_nodes = {node.node_id: node for node in current.nodes}
    previous_edges = {edge.edge_id: edge for edge in previous.edges}
    current_edges = {edge.edge_id: edge for edge in current.edges}

    added_nodes = tuple(sorted(current_nodes.keys() - previous_nodes.keys()))
    removed_nodes = tuple(sorted(previous_nodes.keys() - current_nodes.keys()))
    changed_nodes = tuple(
        sorted(
            node_id
            for node_id in previous_nodes.keys() & current_nodes.keys()
            if previous_nodes[node_id].content_hash
            != current_nodes[node_id].content_hash
        )
    )
    added_edges = tuple(sorted(current_edges.keys() - previous_edges.keys()))
    removed_edges = tuple(sorted(previous_edges.keys() - current_edges.keys()))
    changed_edges = tuple(
        sorted(
            edge_id
            for edge_id in previous_edges.keys() & current_edges.keys()
            if previous_edges[edge_id].content_hash
            != current_edges[edge_id].content_hash
        )
    )
    changed_roots = set(added_nodes) | set(removed_nodes) | set(changed_nodes)
    edge_targets = {
        previous_edges[edge_id].target_id
        for edge_id in (*removed_edges, *changed_edges)
        if edge_id in previous_edges
    } | {
        current_edges[edge_id].target_id
        for edge_id in (*added_edges, *changed_edges)
        if edge_id in current_edges
    }
    impacted = (
        edge_targets
        | _downstream(
            previous,
            changed_roots | edge_targets,
        )
        | _downstream(
            current,
            changed_roots | edge_targets,
        )
    )
    impacted.difference_update(changed_roots)
    return GraphDiff(
        previous_graph_id=previous.manifest.graph_id,
        added_nodes=added_nodes,
        removed_nodes=removed_nodes,
        changed_nodes=changed_nodes,
        added_edges=added_edges,
        removed_edges=removed_edges,
        changed_edges=changed_edges,
        impacted_nodes=tuple(sorted(impacted)),
    )


def _downstream(graph: LineageGraph, roots: set[str]) -> set[str]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        adjacency[edge.source_id].add(edge.target_id)
    seen = set(roots)
    queue = deque(roots)
    while queue:
        source = queue.popleft()
        for target in adjacency[source] - seen:
            seen.add(target)
            queue.append(target)
    return seen
