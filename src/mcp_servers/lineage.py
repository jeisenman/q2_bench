"""Focused read-only lineage tools for the production-support MCP."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from mcp.server.mcpserver import MCPServer

from adapters.local import JsonLineageGraphSource
from adapters.postgres import LINEAGE_POSTGRES_DSN_ENV, PostgresLineageStore
from mcp_servers.debug import McpDebugTrace
from observability import current_trace_metadata, traced_operation
from workspaces.data_engineering.workflows.lineage import (
    RADAR_LINEAGE_REPOSITORY,
    LineageNode,
    LineageQueryService,
    LineageQuerySource,
    RepositoryManifest,
    TraversalDirection,
)

LineageOperation = Callable[[LineageQueryService], dict[str, object]]


async def search_lineage_datasets(
    query: str,
    limit: int = 20,
) -> dict[str, object]:
    """Search logical and Snowflake datasets in the latest lineage graph."""

    def operation(service: LineageQueryService) -> dict[str, object]:
        result = service.search_datasets(query, limit=limit)
        return {
            "graph": _manifest(result.manifest),
            "count": len(result.nodes),
            "datasets": [_node_summary(node) for node in result.nodes],
        }

    return await _execute("search_lineage_datasets", operation)


async def get_lineage_upstream(
    node_id: str,
    depth: int = 1,
    limit: int = 100,
) -> dict[str, object]:
    """Traverse bounded upstream lineage from a canonical node identifier."""
    return await _traverse(node_id, TraversalDirection.UPSTREAM, depth, limit)


async def get_lineage_downstream(
    node_id: str,
    depth: int = 1,
    limit: int = 100,
) -> dict[str, object]:
    """Traverse bounded downstream lineage from a canonical node identifier."""
    return await _traverse(node_id, TraversalDirection.DOWNSTREAM, depth, limit)


async def get_lineage_transformation(
    node_id: str,
) -> dict[str, object]:
    """Return full transformation, schema, allocation, and source details."""

    def operation(service: LineageQueryService) -> dict[str, object]:
        result = service.transformation_details(node_id)
        return {
            "graph": _manifest(result.manifest),
            "node": _node_details(result.node),
        }

    return await _execute("get_lineage_transformation", operation)


async def get_lineage_change_history(
    node_id: str,
    limit: int = 20,
) -> dict[str, object]:
    """Return graph commits where one node was created, changed, or removed."""

    def operation(service: LineageQueryService) -> dict[str, object]:
        revisions = service.change_history(node_id, limit=limit)
        return {
            "nodeId": node_id,
            "count": len(revisions),
            "revisions": [
                {
                    "graph": _manifest(revision.manifest),
                    "changeType": revision.change_type,
                    "present": revision.node is not None,
                    "contentHash": revision.content_hash,
                    "node": (
                        _node_summary(revision.node)
                        if revision.node is not None
                        else None
                    ),
                }
                for revision in revisions
            ],
        }

    return await _execute("get_lineage_change_history", operation)


def register_lineage_tools(server: MCPServer) -> None:
    """Register focused lineage discovery tools on an MCP server."""
    server.tool(
        name="search_lineage_datasets",
        description=(
            "Search datasets and Snowflake tables in the latest RADAR "
            "source-derived lineage graph."
        ),
    )(search_lineage_datasets)
    server.tool(
        name="get_lineage_upstream",
        description=(
            "Traverse bounded upstream jobs and datasets from a canonical lineage ID."
        ),
    )(get_lineage_upstream)
    server.tool(
        name="get_lineage_downstream",
        description=(
            "Traverse bounded downstream jobs and datasets from a canonical lineage ID."
        ),
    )(get_lineage_downstream)
    server.tool(
        name="get_lineage_transformation",
        description=(
            "Read schema, transformations, source locations, standard allocation, "
            "and larger-client allocation overrides for one lineage node."
        ),
    )(get_lineage_transformation)
    server.tool(
        name="get_lineage_change_history",
        description=(
            "Read versioned creation, change, and removal history for one lineage node."
        ),
    )(get_lineage_change_history)


async def _traverse(
    node_id: str,
    direction: TraversalDirection,
    depth: int,
    limit: int,
) -> dict[str, object]:
    def operation(service: LineageQueryService) -> dict[str, object]:
        result = service.traverse(
            node_id,
            direction,
            depth=depth,
            limit=limit,
        )
        return {
            "graph": _manifest(result.manifest),
            "root": _node_summary(result.root),
            "direction": result.direction.value,
            "depth": result.depth,
            "truncated": result.truncated,
            "nodeCount": len(result.nodes),
            "edgeCount": len(result.edges),
            "nodes": [_node_summary(node) for node in result.nodes],
            "edges": [edge.to_dict() for edge in result.edges],
        }

    return await _execute(f"get_lineage_{direction.value}", operation)


async def _execute(
    tool_name: str,
    operation: LineageOperation,
) -> dict[str, object]:
    correlation_id = uuid4().hex
    debug = McpDebugTrace(tool_name, correlation_id)
    debug.event("tool.start", source=_source_mode())
    try:
        async with traced_operation(
            f"mcp.{tool_name}",
            attributes={
                "q2.mcp.tool.name": tool_name,
                "q2.agent.correlation_id": correlation_id,
            },
        ):
            service = LineageQueryService(
                _source(),
                repository=RADAR_LINEAGE_REPOSITORY,
            )
            result = await asyncio.to_thread(operation, service)
            result["trace"] = current_trace_metadata()
            debug.event("tool.complete", response_field_count=len(result))
            if debug.enabled:
                result["debug_trace"] = debug.result()
            return result
    except Exception as error:
        debug.event("tool.error", error_type=type(error).__name__)
        raise


def _source() -> LineageQuerySource:
    dsn = os.environ.get(LINEAGE_POSTGRES_DSN_ENV, "")
    if dsn.strip():
        return PostgresLineageStore(dsn)
    return JsonLineageGraphSource.from_environment()


def _source_mode() -> str:
    dsn = os.environ.get(LINEAGE_POSTGRES_DSN_ENV, "")
    return "postgres" if dsn.strip() else "json-artifact"


def _manifest(manifest: RepositoryManifest) -> dict[str, object]:
    return manifest.to_dict()


def _node_summary(node: LineageNode) -> dict[str, object]:
    return {
        "id": node.node_id,
        "kind": node.identifier.kind.value,
        "namespace": node.identifier.namespace,
        "name": node.identifier.name,
        "description": node.description,
        "version": node.version,
        "owners": list(node.owners),
        "fieldCount": len(node.fields),
        "locationCount": len(node.locations),
        "transformationCount": len(node.transformations),
        "enrichmentCount": len(node.enrichments),
    }


def _node_details(node: LineageNode) -> dict[str, Any]:
    return {
        **_node_summary(node),
        "fields": [field.to_dict() for field in node.fields],
        "locations": [location.to_dict() for location in node.locations],
        "transformations": [
            transformation.to_dict() for transformation in node.transformations
        ],
        "sources": [source.to_dict() for source in node.sources],
        "context": node.context.to_dict() if node.context else None,
        "attributes": dict(node.attributes),
        "enrichments": [enrichment.to_dict() for enrichment in node.enrichments],
        "contentHash": node.content_hash,
    }
