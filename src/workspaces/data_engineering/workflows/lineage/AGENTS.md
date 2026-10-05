# Repository lineage workflow

## Purpose

This deterministic workflow extracts the intended DI Pipelines
`l3_main_graph` and `snowflake_ingestion` graph for a maximum-permission
client. Its input is a local DI Pipelines checkout. Its output is an immutable
OpenLineage-compatible graph, a change summary, and an optional PostgreSQL
write. Extraction reads source files and Git metadata only; it never imports
or runs DI Pipelines code.

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

The domain contracts in [`models.py`](models.py) and
[`graph_models.py`](graph_models.py) own graph state. [`ports.py`](ports.py)
defines the injected persistence and read boundaries. [`query.py`](query.py)
provides bounded dataset search, upstream and downstream traversal,
transformation details, and node change history. The PostgreSQL implementation
lives outside this package in `src/adapters/postgres/lineage.py`; local MCP
staging uses `src/adapters/local/lineage.py`.

The workflow is synchronous and deterministic. It has no agent, delegated
subagent, model, or internal concurrency. OpenTelemetry instrumentation is
applies at the MCP composition boundary in `src/mcp_servers/lineage.py`; the
pure extraction and query services do not depend on telemetry SDKs.

## Dependencies

- Internal packages: this lineage package and the injected `LineageStore` and
  `LineageQuerySource` protocols.
- External SDKs: none in the workflow. Git is invoked as a local subprocess
  for revision metadata.
- External services: none during extraction. A configured store may write to
  PostgreSQL after the graph and diff are complete. MCP queries read
  PostgreSQL when configured or a generated local JSON artifact.
- Runtime configuration: the repository path and optional source ref for
  extraction; `LINEAGE_POSTGRES_DSN` or `LINEAGE_GRAPH_PATH` for MCP reads.
- Telemetry: the MCP composition root emits bounded operation spans and local
  lifecycle diagnostics. Graph contracts and parsers remain telemetry-free.

## Workflow

1. Validate and inspect the repository checkout, then create a manifest from
   its commit SHA.
2. Index DAG, task-group, utility, and dataset metadata source files.
3. Scan all main-graph branches for the maximum-permission profile.
4. Resolve the standard allocation for every physical job, then evaluate
   source-defined client IDs and resource sizes to retain the clients whose
   allocation differs.
5. Resolve each task-group call into physical jobs and dependencies.
6. Build logical job, dataset, and final Snowflake table nodes. Collapse
   aggregate and copy jobs that share one canonical dataset identity.
7. Compare the graph with the latest stored graph for the same repository and
   profile.
8. If a store is supplied, atomically persist the graph, normalized entities,
   and diff. Invalid source or Git state fails before persistence. Database
   errors roll back the transaction.
9. The MCP query service reads the latest matching graph for search,
   traversal, and transformation details. Change history reads graph versions
   newest first and compares node content hashes.

The extraction workflow accepts no trace context. MCP queries create bounded
operation spans and return trace IDs when a recording provider is active.
Queries are read-only; the only lineage write is the optional PostgreSQL
sync.

## Verification

Unit tests under
`tests/unit/workspaces/data_engineering/workflows/lineage/` cover identifiers,
source parsing, metadata inheritance, semantic condensation, graph validation,
resource defaults, client allocation overrides, diff impact, and repository
manifests. PostgreSQL and CLI tests cover
idempotency, transaction statements, configuration failures, and artifact
output. Query, local artifact, and MCP tests cover bounded traversal, search,
allocation rendering, history, source selection, and debug lifecycle events.
`uv run python scripts/check.py` runs the complete repository quality suite.

## Change policy

Update this document when extraction scope, canonical identity, condensation,
storage boundaries, side effects, dependencies, workflow order, or telemetry
behavior changes.
