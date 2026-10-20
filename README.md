# Q2 Bench

A Go SDK and MCP API for data-engineering agent workloads. Python is retained
only for Databricks notebooks and the Databricks SDK bridge.

## Requirements

- Go 1.25+
- Python 3.11+ and `uv` for Databricks code and repository checks
- Docker Desktop for the long-running production-support MCP server

## Install

```bash
uv sync
go mod download
uv run pre-commit install
```

Copy the environment templates before using live connectors:

```bash
cp .env.example .env
cp configurations.yaml.example configurations.yaml
```

Credential values belong only in the ignored `.env` file or the environment.
The Go MCP launcher loads `.env` when it exists and preserves variables
already exported in the process environment.

## Go SDK

The main packages are:

```text
domain/                  Provider-neutral contracts
ports/                   Integration interfaces
agents/                  Agent implementations
agentmemory/             Durable-memory policy
workflowharness/         Deterministic workflow runner
workflows/prodsupport/   Production-support policy
adapters/                Airflow, OMS, and Resource Discovery clients
mcpapi/                  Go MCP capability surfaces
cmd/                     Go command entry points
```

List the bundled agents:

```bash
go run ./cmd/agentbench agents
```

## Go MCP API

`q2-mcp` serves these capability sets:

- `airflow`
- `lineage`
- `oms`
- `prod-support`
- `remote-data`
- `resource-discovery`
- `warehouse`

Run a server over stdio:

```bash
go run ./cmd/q2-mcp --server remote-data
```

The read-only `lineage` server and the `prod-support` server expose bounded
lineage search, upstream/downstream traversal, transformation details, and
change-history tools. They read `LINEAGE_GRAPH_PATH`, defaulting to
`var/lineage/di-pipelines.json`. Synchronize the latest complete Semantic
Layer generation from the sibling Researcher checkout before querying:

```bash
go run ./cmd/agentbench semantic-sync --dry-run
go run ./cmd/agentbench semantic-sync
```

The sync validates exact graph/request/response coverage, attaches Researcher
meaning as `q2_semanticMeaning` facets, and atomically replaces the staged
graph. Use `--researcher-root` when the checkout is not at `../researcher`.

Run the production-support server over Streamable HTTP:

```bash
docker compose up -d --build --force-recreate --wait prod-support-mcp
```

The local endpoint is `http://127.0.0.1:8765/mcp`.

Run Snowflake Cortex through the containerized warehouse server:

```bash
docker compose up -d --build --force-recreate --wait warehouse-mcp
```

The warehouse endpoint is `http://127.0.0.1:8766/mcp`. Starting it also starts
the Cortex-only sidecar at `http://127.0.0.1:8767/mcp`. Both default to
deterministic sandbox replay. Dev calls reuse the ignored
`~/projects/ds-airflow/chart/local_connections/de_transforms_snowflake.json`
key-pair connection through a read-only mount. Other environments use the
matching `SNOWFLAKE_<ENVIRONMENT>_*` variables in `.env`.

The warehouse server also exposes `run_cortex_agent`. Pass a fully qualified
Snowflake Cortex Agent name plus an optional `version` such as `VERSION$2`,
`LIVE`, `DEFAULT`, `LAST`, or `FIRST`; omitting it uses Snowflake's default
version. Sandbox agent responses use
`WAREHOUSE_SANDBOX_CORTEX_AGENT_RECORDINGS` and fail closed when no matching
recording exists.

Production follow-up retries require all of the following:

- `PROD_SUPPORT_SOURCE=production`
- an explicit `approval_id`
- retry candidates preserved by the connector-driven skill procedure or
  returned by the compatibility `run_prod_support` façade
- the original US-01 and CA-02 validation URLs

The tool dry-runs and validates the exact Airflow task selection before clearing
failed task instances.

For a confirmed changed dataset, use
`plan_prod_support_dependency_rerun` followed by
`execute_prod_support_dependency_rerun`. This separate flow accepts exact later
DAG run IDs, selects the starting task and downstream descendants with
`only_failed=false`, blocks active tasks, and executes only when the approved
dry-run plan is unchanged. It keeps Airflow `include_future=false` so the
recomputation window cannot expand beyond the listed runs.
Clients that cached the pre-restart tool list can use the dependency mode on
`execute_prod_support_follow_up`; an explicit re-run/dependency direction
activates the same bounded policy.

For interactive live support, the `$prod-support` Markdown procedure calls the
Airflow, Resource Discovery, and OMS MCP connectors directly and performs all
triage in the current agent. It does not route failures to subagents.
`run_prod_support` remains available for compatibility and benchmark callers.

The `prod-support` server also exposes `get_kpo_job_templates` and
`estimate_kpo_resources`, deterministic and network-free static planning
capabilities. The bounded catalog can supply verified job identity,
runner/family routes, and known chunk or concurrency defaults. Measured
runtime-dependent evidence remains mandatory. Estimates return exact byte
components, GiB renderings, CPU guidance, assumptions, warnings, the applied
template, and the effective configuration; they reject contradictions, missing
evidence, and requests above reviewed tiers. Neither tool changes production
allocations. See
[docs/kpo-sizing-estimator.md](docs/kpo-sizing-estimator.md) for formulas and
input semantics.

For measured runtime validation, `prepare_kpo_memory_profile` creates an exact
approval-gated retry candidate and `watch_kpo_task_memory` samples the newer
attempt's Kubernetes memory. Spark profiles follow the driver application's
selector so driver and executor pods are graphed together. The watcher is
read-only, bounded to five minutes per call, and requires the MCP host to have
the regional `kubectl` context and Kubernetes Metrics API access.

## Databricks Python boundary

Python remains only where Databricks requires it:

```text
src/adapters/databricks/
src/databricks_runtime/
src/adapters/local/configuration.py
src/adapters/outbound/data_engineering/
src/workspaces/**/databricks notebook assets and builders
```

The Go `remote-data` MCP server invokes `databricks_runtime.cli` only for
reviewed notebook submission and integration-branch upload. Notebook generation
and all other MCP routing are implemented in Go.

See [docs/go-migration.md](docs/go-migration.md) for the retained boundary.

## Restart after MCP changes

Validate the restart command, then fully recreate the MCP container:

```bash
uv run python scripts/restart_codex_runtime.py --dry-run
uv run python scripts/restart_codex_runtime.py
```

After restart, confirm the container is healthy and
`PROD_SUPPORT_SOURCE=production`.

## Quality

```bash
uv run python scripts/check.py
```

This runs Go formatting, vetting, tests, Python formatting, linting, strict type
checking, retained Databricks tests, and the 400-line file policy.
