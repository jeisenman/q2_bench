---
name: remote-data
description: Build read-only notebooks and query approved Data Engineering Databricks, RA Databricks, ADLS, Snowflake, and production OMS targets.
---

# Remote data

Use the `remote-data` MCP server to query approved remote data locations. Keep
credentials out of notebook source. Return raw evidence without classifying
it.

## Workflow

1. If the target is unclear, call `list_remote_data_targets`.
2. For Data Engineering or RA Databricks, call `make_databricks_notebook`.
   Review the returned SOURCE and keep its `source_sha256`.
3. Run `run_databricks_notebook` only after you review that exact SOURCE. Pass
   its digest and an approved existing cluster ID. The tool returns after it
   submits the one-time run.
4. For bounded ADLS reads, call `make_adls_notebook`. Supported targets are
   dev, staging, US production, and CA production.
5. For bounded read-only SQL, call `make_snowflake_notebook`. It uses
   `prod_us` by default. Use `alpha` or `staging` only when the user requests
   that environment.
6. For raw OMS evidence, call `query_oms` or `query_job_evidence` for
   `pl-oms-us-primary` or `pl-oms-ca-primary`.

## Snowflake setup

Install the optional connector with `uv sync --extra snowflake`. Generated
notebooks read credentials at runtime from environment-prefixed variables,
such as `SNOWFLAKE_PROD_US_ACCOUNT`, `SNOWFLAKE_PROD_US_USER`, and
`SNOWFLAKE_PROD_US_PASSWORD`. Never put credential values in notebook source.

The `warehouse-mcp` executable uses `dev`, `stage`, `prod`, and `sandbox` with
`SNOWFLAKE_<ENVIRONMENT>_*` variables. See `SETUP.md` and
`docs/warehouse-environments.md` in the agentsdk repository for connector,
authenticator, and restart requirements.

OMS classification belongs to production-support logic, not this skill.

## Target guides

Read only the guide for the selected target:

- [Snowflake](references/SNOWFLAKE.md)
- [Databricks](references/DATABRICKS.md)
- [OMS and Airflow task translation](references/OMS.md)
