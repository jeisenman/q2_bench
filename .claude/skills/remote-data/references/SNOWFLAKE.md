# Snowflake

Use this guide to generate a bounded, read-only Snowflake notebook through the
`remote-data` MCP server.

## Select the environment

`make_snowflake_notebook` accepts:

| Environment | Intended use |
| --- | --- |
| `alpha` | Alpha validation |
| `staging` | Preproduction validation |
| `prod_us` | US production; this is the tool default |

Always pass the environment explicitly when the request is not for US
production. Treat `prod_us` as production access even when the statement is
read-only.

The generated notebook uses environment-prefixed variables such as
`SNOWFLAKE_PROD_US_ACCOUNT`, `SNOWFLAKE_PROD_US_USER`, and
`SNOWFLAKE_PROD_US_PASSWORD`. Never put credential values in the statement,
notebook source, logs, or documentation.

## Find the relevant schema and query

Resolve the configured repository root from:

```text
workspaces.data_engineering.repositories.root
```

Then inspect `<repositories.root>/di-pipelines` before writing SQL. Useful
locations include:

- `de-jobs/src/datamart/jobs/snowflake/evolutions/` for versioned DDL;
- `de-jobs/src/datamart/jobs/snowflake/metadata/` for metadata definitions;
- `de-jobs/src/datamart/jobs/snowflake/repeatable/` for repeatable objects;
- `de-jobs/src/datamart/jobs/data_explorer/` for Data Studio queries;
- `dags/precisionlender/dags/snowflake_*.py` for Airflow orchestration.

Use source inspection to identify the database, schema, table, join keys, and
date fields. Do not guess object names from an Airflow task name.

## Generate the notebook

Call `make_snowflake_notebook` with a read-only statement and a bounded result:

```json
{
  "statement": "SELECT * FROM DATABASE.SCHEMA.TABLE ORDER BY UPDATED_AT DESC",
  "environment": "staging",
  "limit": 100
}
```

Allowed leading statements are `SELECT`, `WITH`, `SHOW`, and `DESCRIBE`.
The limit must be between 1 and 10,000. The generator rejects obvious
mutations, but the caller must still review the complete statement before
running the notebook.

Prefer this investigation order:

1. `SHOW` or `DESCRIBE` the object when its shape is uncertain.
2. Select only the columns needed for the question.
3. Filter by client and a bounded date or run window when available.
4. Add deterministic ordering before applying the result limit.
5. Review the generated source, target, and environment before execution.

For portable application queries and deterministic benchmark fixtures, use
`warehouse-mcp` instead. Its environment names are `dev`, `stage`, `prod`, and
`sandbox`, which intentionally differ from this notebook generator.
