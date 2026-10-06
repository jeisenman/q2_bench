"""Deterministic node and edge accumulation for aggregate RADAR lineage."""

from __future__ import annotations

from workspaces.data_engineering.workflows.lineage.enrichments import (
    SourceLocation,
)
from workspaces.data_engineering.workflows.lineage.identifiers import (
    run_file_identifier,
)
from workspaces.data_engineering.workflows.lineage.models import (
    DatasetLocation,
    EdgeKind,
    LineageEdge,
    LineageNode,
)
from workspaces.data_engineering.workflows.lineage.radar_sources import (
    RunFileContract,
)


class RadarGraphAccumulator:
    """Own common graph mutation while a RADAR graph is being assembled."""

    def __init__(self) -> None:
        """Initialize empty deterministic indexes."""
        self._nodes: dict[str, LineageNode] = {}
        self._edges: dict[str, LineageEdge] = {}
        self._contracts: dict[str, RunFileContract] = {}

    def _paths(self, folder: str) -> tuple[str, ...]:
        prefix = f"{folder}/"
        return tuple(
            path for path in sorted(self._contracts) if path.startswith(prefix)
        )

    def _add_file(
        self,
        path: str,
        sources: tuple[SourceLocation, ...] = (),
        description: str | None = None,
        *,
        resource: str = "OperationalADLS",
    ) -> str:
        identifier = run_file_identifier(path)
        existing = self._nodes.get(identifier.value)
        contract = self._contracts.get(path)
        combined_sources = {
            *sources,
            *((contract.source,) if contract is not None else ()),
            *((existing.sources) if existing is not None else ()),
        }
        location = DatasetLocation(resource, f"{{runPath}}/{path}")
        locations = {location, *((existing.locations) if existing else ())}
        self._nodes[identifier.value] = LineageNode(
            identifier=identifier,
            description=description
            or (existing.description if existing else None)
            or f"RADAR run file {path}.",
            version=existing.version if existing else None,
            fields=existing.fields if existing else (),
            locations=tuple(
                sorted(
                    locations,
                    key=lambda item: (
                        item.resource,
                        item.path_convention or "",
                        item.role,
                    ),
                )
            ),
            transformations=existing.transformations if existing else (),
            sources=tuple(
                sorted(combined_sources, key=lambda item: (item.path, item.line))
            ),
            owners=existing.owners if existing else ("precisionlender",),
            context=existing.context if existing else None,
            attributes=existing.attributes if existing else (("runFile", path),),
            enrichments=existing.enrichments if existing else (),
        )
        return identifier.value

    def _depends(self, upstream: str, downstream: str) -> None:
        self._edge(upstream, downstream, EdgeKind.DEPENDS_ON)

    def _edge(
        self,
        source: str,
        target: str,
        kind: EdgeKind,
        attributes: tuple[tuple[str, str], ...] = (),
    ) -> None:
        edge = LineageEdge(source, target, kind, attributes)
        self._edges[edge.edge_id] = edge
