# Cortex environments

Cortex inference resolves against one of four environments. `dev`, `stage`,
and `prod` reach Snowflake through the Go driver. `sandbox` replays recorded
responses.

Only `sandbox` is deterministic, and every result says which environment
produced it.

## Separate inference from deterministic queries

Cortex is model inference, so no fixture can reproduce it. Keeping it behind
its own port stops an LLM call from ending up inside a query a benchmark
asserts on.

## The portability rule

A sandbox result is only evidence about production if the statement means the
same thing in both. `domain.sql_portability` rejects, in **every**
environment:

| Rejected | Use instead |
| --- | --- |
| `SNOWFLAKE.CORTEX.*`, `AI_COMPLETE(...)` | the `CortexInference` port |
| `payload:region` | `payload->>'region'` |
| `LATERAL FLATTEN(...)` | `unnest(...)` |
| `OBJECT_CONSTRUCT(...)` | `json_object(...)` |
| `DATEADD(day, ...)` | an `INTERVAL` expression |
| `CURRENT_TIMESTAMP`, `NOW()` | a bound parameter for the window |
| `RANDOM()`, `UUID_STRING()` | fixture data |

Constructs inside string literals and comments are not flagged.

Snowflake scalar functions whose semantics match but whose names differ —
`IFF`, `NVL`, `NVL2`, `ZEROIFNULL`, `NULLIFZERO`, `CHARINDEX`, `TO_VARCHAR`,
`TO_NUMBER` — are shimmed as DuckDB macros in
[`compat.sql`](../src/adapters/duckdb/compat.sql) and work unchanged.

The rules are enforced at the port boundary, so a non-portable statement
fails when it is written rather than when a benchmark quietly disagrees with
production.

## Configuration

```bash
export WAREHOUSE_ENVIRONMENT=sandbox        # dev | stage | prod | sandbox
export WAREHOUSE_SANDBOX_CORTEX_RECORDINGS=path/to/recordings
export WAREHOUSE_SANDBOX_CORTEX_AGENT_RECORDINGS=path/to/agent-recordings
```

The dev container reuses the ignored ds-airflow Airflow connection:

```text
~/projects/ds-airflow/chart/local_connections/de_transforms_snowflake.json
```

It mounts that file read-only and resolves its account, login, and
`private_key_content` only when a request is made. Set
`DS_AIRFLOW_SNOWFLAKE_CONNECTION_FILE` to override the host path.

Snowflake settings are read per environment, so one process can address
several without ambiguity:

```bash
export SNOWFLAKE_PROD_ACCOUNT=...
export SNOWFLAKE_PROD_USER=...
export SNOWFLAKE_PROD_ROLE=...
export SNOWFLAKE_PROD_WAREHOUSE=...
export SNOWFLAKE_PROD_DATABASE=...
export SNOWFLAKE_PROD_SCHEMA=...
export SNOWFLAKE_PROD_PASSWORD=...          # resolved through SecretProvider
```

Missing settings fail fast and name every variable to set. The credential is
resolved at call time through a `SecretProvider` and never stored on a
settings object.

The Snowflake Go driver is compiled into `warehouse-mcp`.

Supported authenticators are `snowflake_jwt`, `snowflake`, `oauth`, and `pat`.
JWT reads a PKCS#8 RSA key from an Airflow connection file. Password
authentication resolves `SNOWFLAKE_<ENVIRONMENT>_PASSWORD`; OAuth and PAT
resolve `SNOWFLAKE_<ENVIRONMENT>_TOKEN`. Interactive browser authentication
is not supported by the container.

## Sandbox recordings

The sandbox recording directory contains one JSON file per captured request:

```json
{
  "model": "<approved-model>",
  "prompt": "Summarize this failure.",
  "temperature": 0,
  "text": "Recorded completion.",
  "token_count": 4
}
```

The request identity includes model, prompt, and temperature. An unrecorded
request fails instead of inventing an answer.

## MCP routes

`warehouse-mcp` exposes three tools:

- `run_cortex_complete` — one Cortex completion. Reports whether the response
  was live or replayed.
- `count_cortex_tokens` — one bounded tokenizer count without inference.
- `run_cortex_agent` — one Cortex Agent request with an optional immutable
  version, alias, or system shortcut such as `VERSION$2`, `LIVE`, `DEFAULT`,
  `LAST`, or `FIRST`. Sandbox responses are keyed by agent, version, request
  body, and thread-creation flag.

Omitting `version` uses the agent's Snowflake `DEFAULT` version. The route
returns the requested selector so callers can record whether they targeted a
committed version, alias, or mutable live/default pointer. The response is
always non-streaming because `DATA_AGENT_RUN` is a non-streaming wrapper.

Every route takes an optional `environment` that overrides the configured
default.

## Container

Rebuild and recreate the service after code, dependency, prompt, environment,
or configuration changes:

```bash
docker compose up -d --build --force-recreate --wait warehouse-mcp
```

This starts both the warehouse service and its Cortex-only sidecar. The
Streamable HTTP endpoints are `http://127.0.0.1:8766/mcp` for warehouse and
`http://127.0.0.1:8767/mcp` for Cortex.
