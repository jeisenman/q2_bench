# Repository lineage workflow

## Purpose

This deterministic workflow extracts the RADAR file pipeline through DI
Pipelines and Snowflake. Its inputs are explicit local checkouts for RADAR
notebooks, libraries, ADF, DataIngress, calculation engine, and DI Pipelines.
Its output is an immutable OpenLineage-compatible graph, a change summary,
and an optional PostgreSQL write. Extraction reads source files and Git
metadata only; it never imports or runs source repository code.

## Architecture

[`workflow.py`](workflow.py) is the public composition root.
[`repository.py`](repository.py) creates the version manifest.
[`source.py`](source.py), [`ast_values.py`](ast_values.py), and the
`physical*.py` modules provide bounded static Python analysis.
[`allocations.py`](allocations.py) evaluates the main graph for the standard
client and each allocation-relevant client UUID. [`operator_defaults.py`](operator_defaults.py)
reads shared Kubernetes and Spark defaults from the operator framework.
[`main_graph.py`](main_graph.py) scans every feature-gated path.
[`metadata.py`](metadata.py) resolves dataset classes, schemas, descriptions,
versions, and Snowflake destinations. [`builder.py`](builder.py) condenses
physical aggregate and copy tasks into semantic datasets. [`diff.py`](diff.py)
compares immutable graph versions and computes downstream impact.

[`radar_sources.py`](radar_sources.py) resolves generated loader/outputter
helpers and notebook calls. [`radar_engine_sources.py`](radar_engine_sources.py)
reads ADF activities, DataIngress source anchors, and public engine calculation
contracts. [`radar_graph.py`](radar_graph.py) composes the structural stages,
while [`radar_accumulator.py`](radar_accumulator.py) owns deterministic file
and edge merging. Engine calculations are `NodeEnrichment` values and never
create structural nodes or edges.

The domain contracts in [`models.py`](models.py) and
[`graph_models.py`](graph_models.py) own graph state. [`ports.py`](ports.py)
defines the injected persistence and read boundaries. [`query.py`](query.py)
provides bounded dataset search, upstream and downstream traversal,
transformation details, and node change history. The PostgreSQL implementation
lives outside this package in `src/adapters/postgres/lineage.py`; local MCP
staging uses `src/adapters/local/lineage.py`.

The workflow is synchronous and deterministic. It has no agent, delegated
subagent, model, or internal concurrency. OpenTelemetry instrumentation is
applied at the MCP composition boundary in `src/mcp_servers/lineage.py`; the
pure extraction and query services do not depend on telemetry SDKs.

## Dependencies

- Internal packages: this lineage package and the injected `LineageStore` and
  `LineageQuerySource` protocols.
- External SDKs: none in the workflow. Git is invoked as a local subprocess
  for revision metadata.
- Source repositories: six local Git checkouts supplied through
  `RadarRepositories`.
- External services: none during extraction. A configured store may write to
  PostgreSQL after the graph and diff are complete. MCP queries read
  PostgreSQL when configured or a generated local JSON artifact.
- Runtime configuration: six repository paths and an optional aggregate source
  label; `LINEAGE_POSTGRES_DSN` or `LINEAGE_GRAPH_PATH` for MCP reads.
- Telemetry: the MCP composition root emits bounded operation spans and local
  lifecycle diagnostics. Graph contracts and parsers remain telemetry-free.

## Workflow

1. Validate and inspect all source checkouts, then create an aggregate manifest
   from their commit SHAs and refs.
2. Resolve RADAR run files from DataIngress XML, generated Python file helpers,
   executable notebook calls, and ADF activity declarations.
3. Build upload, extraction, mapping, transform, DTO mapping, calculation,
   DatabaseOutput, and DataEngineeringOutput stages. Attach engine calculations
   only as enrichment on the calculation job.
4. Index DI DAG, task-group, utility, and dataset metadata source files.
5. Scan all main-graph branches for the maximum-permission profile.
6. Resolve the standard allocation for every physical job, then evaluate
   source-defined client IDs and resource sizes to retain the clients whose
   allocation differs.
7. Resolve each task-group call into physical jobs and dependencies.
8. Build logical job, dataset, and final Snowflake table nodes. Collapse
   aggregate and copy jobs that share one canonical dataset identity.
9. Link every statically resolved DI `raFile` to its RADAR run-file dataset.
10. Compare the graph with the latest stored graph for the same repository and
   profile.
11. If a store is supplied, atomically persist the graph, normalized entities,
   and diff. Invalid source or Git state fails before persistence. Database
   errors roll back the transaction.
12. The MCP query service reads the latest matching graph for search,
   traversal, and transformation details. Change history reads graph versions
   newest first and compares node content hashes.

The extraction workflow accepts no trace context. MCP queries create bounded
operation spans and return trace IDs when a recording provider is active.
Queries are read-only; the only lineage write is the optional PostgreSQL
sync.

## Verification

Unit tests under
`tests/unit/workspaces/data_engineering/workflows/lineage/` cover identifiers,
source parsing, RADAR file chaining, enrichment isolation, metadata
inheritance, semantic condensation, graph validation, resource defaults,
client allocation overrides, diff impact, and aggregate repository manifests.
PostgreSQL and CLI tests cover
idempotency, transaction statements, configuration failures, and artifact
output. Query, local artifact, and MCP tests cover bounded traversal, search,
allocation rendering, history, source selection, and debug lifecycle events.
`uv run python scripts/check.py` runs the complete repository quality suite.

## Change policy

Update this document when extraction scope, canonical identity, condensation,
storage boundaries, side effects, dependencies, workflow order, or telemetry
behavior changes.
