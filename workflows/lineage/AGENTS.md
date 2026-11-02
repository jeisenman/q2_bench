# Lineage query workflow

## Purpose

This package provides deterministic, read-only queries over the generated
OpenLineage-compatible repository graph. Structural extraction and versioning
live in `workflows/lineagecheck`; optional Researcher ingestion lives in
`workflows/semanticsync`. This package serves bounded
search, traversal, node-detail, and history operations.

## Architecture

- `models.go` contains the provider-neutral graph contracts, artifact
  decoding, and compact synchronized semantic-meaning projection.
- `source.go` owns the injected graph source and local JSON-artifact loading.
- `query.go` owns validation, deterministic ordering, bounded traversal, and
  change classification.

The MCP composition layer lives in `mcpapi/lineage.go`. It translates typed
MCP inputs and outputs to this package without introducing provider or MCP
dependencies into the workflow.

## Dependencies

- Standard-library JSON and filesystem access only.
- The generated artifact path is selected by `LINEAGE_GRAPH_PATH` and defaults
  to `var/lineage/di-pipelines.json`. `agentbench semantic-sync` stages the
  newest complete Researcher Semantic Layer snapshot at that path.
- The package does not execute source repositories, call external services, or
  mutate graph state.
- `LINEAGE_STORE_PATH` selects the independently maintained local snapshot
  source at the MCP composition boundary. With no store selected, existing
  `LINEAGE_GRAPH_PATH` behavior is preserved.

## Workflow

1. Load and validate one graph artifact per query.
2. Validate query values and enforce search, traversal, and history bounds.
3. Return source manifest metadata with every result.
4. Sort matches, nodes, and edges by stable identifiers.

Local artifacts contain one graph version, so local history reports the
current node as `created` when present. A multi-version source can implement
the same `QuerySource` interface to provide changed and removed revisions.
`lineagecheck.Store` implements that interface for local published versions.

## Verification

Unit tests cover artifact decoding, malformed graphs, search matching,
traversal bounds, missing nodes, and local history behavior. The MCP tests
verify registration, read-only annotations, and tool names.
