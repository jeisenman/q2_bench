# Warehouse environments

Warehouse reads and Cortex inference resolve against one of four
environments. `dev`, `stage`, and `prod` reach Snowflake through the Python
connector. `sandbox` is served locally by DuckDB over CSV fixtures whose
schemas mirror the real warehouse.

Only `sandbox` is deterministic, and every result says which environment
produced it.

## Two ports, because only one of them can be deterministic

| Port | Backends | Double |
| --- | --- | --- |
| `WarehouseQuery` | Snowflake, DuckDB sandbox | CSV fixtures reproduce the data exactly |
| `CortexInference` | Snowflake Cortex, recorded replay | responses captured once, replayed by request key |

Cortex is model inference, so no fixture can reproduce it. Keeping it behind
its own port stops an LLM call from ending up inside a query a benchmark
asserts on.

## The portability rule

A sandbox result is only evidence about production if the statement means the
same thing in both. `domain.sql_portability` rejects, in **every**
environment:

| Rejected | Use instead |
| --- | --- |
| `SNOWFLAKE.CORTEX.*` | the `CortexInference` port |
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
export WAREHOUSE_SANDBOX_FIXTURES=path/to/fixtures
export WAREHOUSE_SANDBOX_CORTEX_RECORDINGS=path/to/recordings
```

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

The Snowflake connector is an optional extra:

```bash
uv sync --extra snowflake
```

## Fixtures

A fixture directory holds `schema.yaml` and one CSV per table:

```yaml
tables:
  - schema: ANALYTICS
    name: FAILED_JOBS
    data: analytics.failed_jobs.csv
    columns:
      - {name: CLIENT_ID, type: VARCHAR}
      - {name: CLIENT_CODE, type: TEXT}
      - {name: FAILED_AT, type: TIMESTAMP_TZ}
      - {name: ROW_COUNT, type: NUMBER}
      - {name: PAYLOAD, type: VARIANT}
```

Types use the warehouse vocabulary and are declared explicitly — inference
never runs, so a fixture edit cannot silently change a column's type. `NUMBER`
means `NUMBER(38,0)`, matching Snowflake. An empty CSV field loads as `NULL`,
not an empty string. The CSV header must match the declared columns.

Each fixture set carries a content digest, so a case pins the exact data it
was written against.

## Anonymizing production data into a fixture

Real production data makes the best benchmark and cannot be committed.
`benchmarks/anonymization.py` rewrites it under a per-fixture-set salt:

| Strategy | Effect |
| --- | --- |
| `keep` | preserve exactly |
| `redact` | replace with `[redacted]` |
| `drop` | replace with `NULL`, keeping the column |
| `pseudonym` | surrogate preserving length and character class |
| `uuid` | surrogate UUID, so prefixes and joins still behave |
| `generalize` | reduce precision, e.g. timestamp to date |

Two properties are enforced. The same value and salt always produce the same
output, so a rebuild is byte-identical. One identifier maps to one pseudonym
in every table, so joins that worked in production still work in the fixture.

Every column needs an explicit strategy. An undeclared column is an error, not
a silent `keep`, so a new production column cannot leak into a committed
fixture.

## MCP routes

`warehouse-mcp` exposes three tools:

- `run_warehouse_query` — one read-only, portable statement with bound
  parameters. Returns rows, the environment, and whether it was deterministic.
  A non-portable statement comes back as a structured error naming each
  violated rule and its fix.
- `run_cortex_complete` — one Cortex completion. Reports whether the response
  was live or replayed.
- `describe_warehouse_table` — the typed columns of one table.

Every route takes an optional `environment` that overrides the configured
default.

## Contract tests

`tests/contract/ports/test_warehouse_contract.py` runs one behavioral suite
against every backend. DuckDB always runs. Snowflake runs when configured:

```bash
export WAREHOUSE_CONTRACT_ENVIRONMENT=dev
uv run pytest tests/contract/ports/test_warehouse_contract.py
```

Without that configuration the Snowflake cases skip with an actionable
reason. This suite is what keeps the sandbox honest: a backend that drifts
fails here instead of inside a benchmark.
