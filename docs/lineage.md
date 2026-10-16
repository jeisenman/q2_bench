# RADAR repository lineage

The lineage workflow statically materializes the RADAR run path and its
downstream DI Pipelines graph as one versioned, OpenLineage-compatible graph.
It reads six local checkouts: `radar-notebooks`, `radar-libraries`,
`radar-adf-pipeline`, `pl-dataingress`, `pl-calculation-engine`, and
`di-pipelines`. It does not import or execute their application code.

## Current scope

The extraction profile is an all-client static union. Client-specific RADAR
notebooks and all feature-gated DI paths are included. The graph follows:

`ClientUploadedFiles -> RawInputs -> MappingResults -> TransformResults ->
computable DTOs -> EngineResults -> DatabaseOutput/DataEngineering ->
DI Pipelines -> Snowflake`

The graph contains:

- extraction, mapping, and transform notebook calls resolved through the
  generated RADAR loader and outputter library;
- ApplicationInput, RelationshipServiceInput, MappingResults,
  TransformResults, EngineResults, DatabaseOutput, and DataEngineering files
  declared by the DataIngress schema;
- ADF activity evidence for each orchestration stage;
- DataIngress DTO mapping, calculation coordination, DatabaseOutput, and
  DataEngineeringOutput jobs;
- public RADAR engine `Calculate*` contracts as enrichment records on the
  engine job only;
- `raFile` edges from RADAR run files into the DI Pipelines task group;
- logical task-group jobs and DAG dependencies from `l3_main_graph.py`;
- custom operator activities and their mechanical dependencies;
- each job's standard compute allocation, including shared Spark and
  Kubernetes defaults;
- named clients whose source-resolved allocation differs from that standard,
  with their client UUID, resource-size tag, and complete allocation;
- dataset schema, description, version, and Snowflake mapping metadata;
- final Snowflake load jobs, tables, and columns from
  `snowflake_ingestion.py`;
- source locations prefixed by repository and deterministic derived
  explanations.

Engine methods and formulas do not become graph nodes or edges. They are
non-structural `enrichments` returned with the engine job's transformation
details. Runtime executions, values, Event Bus transport, and PL Application
internals remain outside the static graph.

## Canonical identifiers

Every node uses an OpenLineage-style `namespace` and `name`. The materialized
graph prefixes those values with the entity kind to make a single stable
database key.

| Entity | Namespace | Name example |
| --- | --- | --- |
| Logical dataset | `q2://data-engineering` | `primary/pl_andi/engagement/plchatengagements` |
| Airflow job | `q2://data-engineering/airflow` | `l3_main_graph/andi` |
| RADAR job | `q2://data-engineering/radar` | `pl_dataingress/database_output` |
| RADAR run file | `q2://data-engineering` | `databaseoutput/dbstagingrelationshipnew_csv` |
| Snowflake table | `snowflake://q2/data-engineering` | `client_data_mart.monthly_financials` |

Dataset identity comes from stage plus logical dataset path. Physical
materializations are locations on that dataset. For example, an aggregate
task followed by internal ADLS and client data-mart copy tasks produces one
logical dataset node with three transformations and its materialization
locations.

## Resource allocations

The extractor first evaluates `l3_main_graph` for a normal client UUID that
does not occur in source. That result is each job's standard allocation. It
then evaluates the graph for client UUIDs declared in the client resource-tag
map, centralized allocation helpers, and task-group source. A client appears
under `largerClients` only when its resolved compute backend, container
resources, Spark configuration, or Spark sizing variables differ from the
standard.

Client names and `large` or `xlarge` tags come from
`clients_metadata_airflow.py`; explicitly overridden clients absent from that
map retain their source comment when available and use the `normal` tag.
Shared Spark driver and executor defaults and the default Kubernetes pod
request are parsed from `dag-utils/operators.py`, so a change to those
framework defaults changes the generated graph.

## Versioning and changes

The aggregate manifest records every source repository, full commit SHA, and
checked-out ref under `sourceRepositories`. Its top-level 40-character commit
is a deterministic digest of those revisions. Graph IDs are deterministic for
that digest, profile, and extractor version, so a change to any component
produces a new immutable graph version.

The workflow compares each graph with the latest stored graph for the same
repository and profile. It records added, removed, and changed nodes and
edges, plus downstream nodes reached from changed or removed nodes. Content
hashes exclude generation time.

## PostgreSQL storage

Apply [`002_lineage.sql`](../migrations/postgres/002_lineage.sql) before
persisting graphs to PostgreSQL. The migration stores the full review artifact
and normalized graph, node, edge, and diff rows. The current Go MCP query
workflow reads the generated JSON artifact directly; PostgreSQL-backed query
history remains a future adapter.

Run a local review extraction:

```bash
uv run agentbench lineage-sync \
  --source-ref static-analysis \
  --dry-run \
  --output var/lineage/radar-lineage.json
```

The defaults expect all six repositories as siblings of this checkout.
Explicit alternatives are available through `--repository`,
`--radar-notebooks-repository`, `--radar-libraries-repository`,
`--radar-adf-repository`, `--data-ingress-repository`, and
`--engine-repository`.

Persist a graph by setting `LINEAGE_POSTGRES_DSN` and omitting `--dry-run`.
The write is atomic and idempotent for repository, commit, profile, and
extractor version.

## MCP tools

The Go `lineage` server and the existing `prod-support-mcp` server expose the
staged lineage through five read-only tools:

- `search_lineage_datasets` searches logical datasets and final Snowflake
  tables by canonical ID, name, description, or field name.
- `get_lineage_upstream` and `get_lineage_downstream` traverse a bounded
  number of graph levels and nodes.
- `get_lineage_transformation` returns schema, physical locations, source
  locations, mechanical transformations, engine enrichments, standard job
  allocation, and larger-client allocation overrides.
- `get_lineage_change_history` returns the commits where a node was created,
  changed, or removed.

The Go implementation reads `LINEAGE_GRAPH_PATH`, which defaults to
`var/lineage/di-pipelines.json`. Docker Compose mounts that path into the
MCP container. The current JSON source exposes the checked-in/generated graph
as the latest version; change-history queries become richer when a versioned
source adapter is added. Regenerate the artifact whenever any source checkout
changes.

Every response identifies the repository commit and extraction profile.
Search and traversal limits are validated before reading data. MCP requests
are instrumented with bounded OpenTelemetry metadata and include
`debug_trace` lifecycle events when `Q2_MCP_DEBUG=1`.

## GitHub automation

[`lineage.yml`](../.github/workflows/lineage.yml) checks out the five
master branches plus calculation engine `develop`, applies the migration,
persists the graph, and uploads the JSON artifact. It runs from:

- a `di-pipelines-master-push` repository dispatch sent by DI Pipelines;
- a `radar-lineage-source-push` dispatch from another source repository;
- an hourly reconciliation schedule;
- manual dispatch;
- changes to the lineage implementation in this repository.

GitHub must provide `DI_PIPELINES_READ_TOKEN` and
`LINEAGE_POSTGRES_DSN` repository secrets.
