"""Read-only search and traversal over versioned lineage graphs."""

from __future__ import annotations

from collections import deque

from workspaces.data_engineering.workflows.lineage.graph_models import LineageGraph
from workspaces.data_engineering.workflows.lineage.models import (
    LineageEdge,
    LineageNode,
    NodeKind,
)
from workspaces.data_engineering.workflows.lineage.ports import LineageQuerySource
from workspaces.data_engineering.workflows.lineage.query_models import (
    LineageNodeDetails,
    LineageRevision,
    LineageSearch,
    LineageTraversal,
    TraversalDirection,
)
from workspaces.data_engineering.workflows.lineage.repository import (
    MAXIMUM_PERMISSIONS_PROFILE,
)

DEFAULT_LINEAGE_REPOSITORY = "precisionlender/di-pipelines"
MAX_SEARCH_RESULTS = 100
MAX_TRAVERSAL_DEPTH = 10
MAX_TRAVERSAL_NODES = 500
MAX_HISTORY_RESULTS = 100


class LineageQueryError(ValueError):
    """Raised when a lineage query is invalid or has no graph to inspect."""

    @classmethod
    def missing_node(cls, node_id: str) -> LineageQueryError:
        """Create an error for an unknown canonical node identifier."""
        return cls(f"lineage node does not exist: {node_id}")

    @classmethod
    def missing_graph(cls, repository: str, profile: str) -> LineageQueryError:
        """Create an error when the requested graph has not been staged."""
        return cls(f"no lineage graph is available for {repository} ({profile})")

    @classmethod
    def empty_value(cls, name: str) -> LineageQueryError:
        """Create an error for an empty query value."""
        return cls(f"{name} must not be empty")

    @classmethod
    def outside_bounds(
        cls,
        name: str,
        maximum: int,
    ) -> LineageQueryError:
        """Create an error for a query bound outside the supported range."""
        return cls(f"{name} must be between 1 and {maximum}")


class LineageQueryService:
    """Search and traverse immutable graphs supplied through a typed port."""

    def __init__(
        self,
        source: LineageQuerySource,
        *,
        repository: str = DEFAULT_LINEAGE_REPOSITORY,
        profile: str = MAXIMUM_PERMISSIONS_PROFILE,
    ) -> None:
        """Initialize the service for one repository extraction profile."""
        self._source = source
        self._repository = _required("repository", repository)
        self._profile = _required("profile", profile)

    def search_datasets(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> LineageSearch:
        """Return matching datasets from the latest stored graph."""
        needle = _required("query", query).casefold()
        bounded = _bounded("limit", limit, MAX_SEARCH_RESULTS)
        graph = self._latest()
        matches = [
            node
            for node in graph.nodes
            if node.identifier.kind is NodeKind.DATASET and _matches(node, needle)
        ]
        return LineageSearch(
            manifest=graph.manifest,
            nodes=tuple(
                sorted(matches, key=lambda node: _search_key(node, needle))[:bounded]
            ),
        )

    def traverse(
        self,
        node_id: str,
        direction: TraversalDirection,
        *,
        depth: int = 1,
        limit: int = 100,
    ) -> LineageTraversal:
        """Return a bounded upstream or downstream traversal."""
        root_id = _required("node_id", node_id)
        bounded_depth = _bounded("depth", depth, MAX_TRAVERSAL_DEPTH)
        bounded_limit = _bounded("limit", limit, MAX_TRAVERSAL_NODES)
        graph = self._latest()
        nodes = {node.node_id: node for node in graph.nodes}
        root = nodes.get(root_id)
        if root is None:
            raise LineageQueryError.missing_node(root_id)
        reached, edges, truncated = _walk(
            graph,
            root_id,
            direction,
            bounded_depth,
            bounded_limit,
        )
        return LineageTraversal(
            manifest=graph.manifest,
            root=root,
            direction=direction,
            depth=bounded_depth,
            nodes=tuple(nodes[node_id] for node_id in sorted(reached)),
            edges=tuple(sorted(edges, key=lambda edge: edge.edge_id)),
            truncated=truncated,
        )

    def transformation_details(self, node_id: str) -> LineageNodeDetails:
        """Return one node with mechanical transformations and allocations."""
        requested = _required("node_id", node_id)
        graph = self._latest()
        node = next((item for item in graph.nodes if item.node_id == requested), None)
        if node is None:
            raise LineageQueryError.missing_node(requested)
        return LineageNodeDetails(manifest=graph.manifest, node=node)

    def change_history(
        self,
        node_id: str,
        *,
        limit: int = 20,
    ) -> tuple[LineageRevision, ...]:
        """Return commits where one node was created, changed, or removed."""
        requested = _required("node_id", node_id)
        bounded = _bounded("limit", limit, MAX_HISTORY_RESULTS)
        graphs = self._source.history(
            self._repository,
            self._profile,
            bounded + 1,
        )
        revisions: list[LineageRevision] = []
        for index, graph in enumerate(graphs[:bounded]):
            current = _node(graph, requested)
            older = (
                _node(graphs[index + 1], requested) if index + 1 < len(graphs) else None
            )
            change_type = _change_type(current, older)
            if change_type is None:
                continue
            revisions.append(
                LineageRevision(
                    manifest=graph.manifest,
                    change_type=change_type,
                    node=current,
                    content_hash=current.content_hash if current else None,
                )
            )
        return tuple(revisions)

    def _latest(self) -> LineageGraph:
        graph = self._source.latest(self._repository, self._profile)
        if graph is None:
            raise LineageQueryError.missing_graph(self._repository, self._profile)
        return graph


def _walk(
    graph: LineageGraph,
    root_id: str,
    direction: TraversalDirection,
    depth: int,
    limit: int,
) -> tuple[set[str], set[LineageEdge], bool]:
    adjacency: dict[str, list[tuple[str, LineageEdge]]] = {}
    for edge in graph.edges:
        source, target = (
            (edge.target_id, edge.source_id)
            if direction is TraversalDirection.UPSTREAM
            else (edge.source_id, edge.target_id)
        )
        adjacency.setdefault(source, []).append((target, edge))
    reached: set[str] = set()
    selected_edges: set[LineageEdge] = set()
    queue = deque([(root_id, 0)])
    truncated = False
    while queue:
        current, current_depth = queue.popleft()
        if current_depth >= depth:
            continue
        for target, edge in sorted(
            adjacency.get(current, ()),
            key=lambda item: (item[0], item[1].edge_id),
        ):
            if target in reached or target == root_id:
                continue
            if len(reached) >= limit:
                truncated = True
                break
            reached.add(target)
            selected_edges.add(edge)
            queue.append((target, current_depth + 1))
        if truncated:
            break
    return reached, selected_edges, truncated


def _matches(node: LineageNode, needle: str) -> bool:
    values = (
        node.node_id,
        node.identifier.name,
        node.description or "",
        *(field.name for field in node.fields),
    )
    return any(needle in value.casefold() for value in values)


def _search_key(node: LineageNode, needle: str) -> tuple[int, str]:
    name = node.identifier.name.casefold()
    if name == needle or node.node_id.casefold() == needle:
        rank = 0
    elif name.startswith(needle):
        rank = 1
    elif needle in name:
        rank = 2
    else:
        rank = 3
    return rank, node.node_id


def _node(graph: LineageGraph, node_id: str) -> LineageNode | None:
    return next((node for node in graph.nodes if node.node_id == node_id), None)


def _change_type(
    current: LineageNode | None,
    older: LineageNode | None,
) -> str | None:
    if current is None and older is None:
        return None
    if current is None:
        return "removed"
    if older is None:
        return "created"
    return "changed" if current.content_hash != older.content_hash else None


def _required(name: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise LineageQueryError.empty_value(name)
    return normalized


def _bounded(name: str, value: int, maximum: int) -> int:
    if not 1 <= value <= maximum:
        raise LineageQueryError.outside_bounds(name, maximum)
    return value
