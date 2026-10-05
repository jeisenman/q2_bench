# DI Pipelines repository lineage

The lineage workflow statically materializes the intended DI Pipelines
`l3_main_graph` and `snowflake_ingestion` paths as a versioned,
OpenLineage-compatible graph. It does not import Airflow, Spark, or DI
Pipelines modules, so extraction does not execute repository code or read
runtime credentials.

## Current scope

The extraction profile assumes one client with every permission and feature
flag enabled. Both branches of source-controlled feature conditions are
included. The graph contains:

- logical task-group jobs and DAG dependencies from `l3_main_graph.py`;
- custom operator activities and their mechanical dependencies;
- each job's standard compute allocation, including shared Spark and
  Kubernetes defaults;
- named clients whose source-resolved allocation differs from that standard,
  with their client UUID, resource-size tag, and complete allocation;
- dataset schema, description, version, and Snowflake mapping metadata;
- final Snowflake load jobs, tables, and columns from
  `snowflake_ingestion.py`;
- source locations and deterministic derived explanations.

Runtime Airflow comparison, PL Application DTOs, Data Ingress XML and ADF,
and the Event Bus transport are outside this first graph. The canonical
identifier and extractor boundaries allow those sources to add evidence to
the same datasets later.

## Canonical identifiers

Every node uses an OpenLineage-style `namespace` and `name`. The materialized
graph prefixes those values with the entity kind to make a single stable
database key.

| Entity | Namespace | Name example |
| --- | --- | --- |
| Logical dataset | `q2://data-engineering` | `primary/pl_andi/engagement/plchatengagements` |
| Airflow job | `q2://data-engineering/airflow` | `l3_main_graph/andi` |
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

The manifest records repository name, full commit SHA, source ref, extraction
profile, extractor version, and generation time. Graph IDs are deterministic
for repository, commit, profile, and extractor version. A new DI Pipelines
master commit therefore produces a new immutable graph version.

The workflow compares each graph with the latest stored graph for the same
repository and profile. It records added, removed, and changed nodes and
edges, plus downstream nodes reached from changed or removed nodes. Content
hashes exclude generation time.

## PostgreSQL storage

Apply [`002_lineage.sql`](../migrations/postgres/002_lineage.sql) before the
first run. It stores the full review artifact and normalized graph, node,
edge, and diff rows. The normalized tables support later dataset search and
upstream or downstream MCP tools without reparsing JSON.

Run a local review extraction:

```bash
uv run agentbench lineage-sync \
  --repository ../di-pipelines \
  --source-ref master \
  --dry-run \
  --output var/lineage/di-pipelines.json
```

Persist a graph by setting `LINEAGE_POSTGRES_DSN` and omitting `--dry-run`.
The write is atomic and idempotent for repository, commit, profile, and
extractor version.

## MCP tools

The existing `prod-support-mcp` server exposes the staged lineage through
five read-only tools:

- `search_lineage_datasets` searches logical datasets and final Snowflake
  tables by canonical ID, name, description, or field name.
- `get_lineage_upstream` and `get_lineage_downstream` traverse a bounded
  number of graph levels and nodes.
- `get_lineage_transformation` returns schema, physical locations, source
  locations, mechanical transformations, standard job allocation, and
  larger-client allocation overrides.
- `get_lineage_change_history` returns the commits where a node was created,
  changed, or removed.

When `LINEAGE_POSTGRES_DSN` is configured, the MCP reads immutable graph
versions from PostgreSQL. Otherwise it reads
`LINEAGE_GRAPH_PATH`, which defaults to
`var/lineage/di-pipelines.json`. Docker Compose mounts that path into the MCP
container. Regenerate the artifact with the local review extraction command
above whenever the DI Pipelines checkout changes.

Every response identifies the repository commit and extraction profile.
Search and traversal limits are validated before reading data. MCP requests
are instrumented with bounded OpenTelemetry metadata and include
`debug_trace` lifecycle events when `Q2_MCP_DEBUG=1`.

## GitHub automation

[`lineage.yml`](../.github/workflows/lineage.yml) checks out DI Pipelines
master, applies the migration, persists the graph, and uploads the JSON
artifact. It runs from:

- a `di-pipelines-master-push` repository dispatch sent by DI Pipelines;
- an hourly reconciliation schedule;
- manual dispatch;
- changes to the lineage implementation in this repository.

GitHub must provide `DI_PIPELINES_READ_TOKEN` and
`LINEAGE_POSTGRES_DSN` repository secrets.
