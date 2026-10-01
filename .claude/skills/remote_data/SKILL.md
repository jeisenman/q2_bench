---
name: remote_data
description: Build read-only notebooks and query approved Data Engineering Databricks, RA Databricks, ADLS, Snowflake, and production OMS targets.
---

# Remote data

Use the `remote-data` MCP server for querying approved remote data locations.
Keep credentials out of notebook source and return raw evidence without
classifying it.

## Workflow

1. Call `list_remote_data_targets` when the target is not already explicit.
2. Use `make_databricks_notebook` for Data Engineering or RA Databricks code.
   Review the returned SOURCE and retain its `source_sha256`.
3. Use `run_databricks_notebook` only after reviewing that exact source. Pass
   its digest and an approved existing cluster ID; the tool returns after the
   one-time run is submitted.
4. Use `make_adls_notebook` for bounded reads from dev, staging, US production,
   or CA production ADLS.
5. Use `make_snowflake_notebook` for bounded read-only SQL. It defaults to
   `prod_us`; pass `alpha` or `staging` only when the user explicitly requests
   another environment.
6. Use `query_oms` or `query_job_evidence` only for raw OMS evidence from
   `pl-oms-us-primary` or `pl-oms-ca-primary`.

## Snowflake setup

Install the optional connector with `uv sync --extra snowflake`. Generated
notebooks read credentials at runtime from environment-prefixed variables such
as `SNOWFLAKE_PROD_US_ACCOUNT`, `SNOWFLAKE_PROD_US_USER`, and
`SNOWFLAKE_PROD_US_PASSWORD`; never write their values into notebook source.

The executable `warehouse-mcp` uses the environment vocabulary `dev`, `stage`,
`prod`, and `sandbox` with `SNOWFLAKE_<ENVIRONMENT>_*` variables. See
`SETUP.md` and `docs/warehouse-environments.md` in the agentsdk repository for
the complete connector, authenticator, and restart requirements.

OMS classification belongs to production-support logic, not this skill.

## Target guides

Read only the guide for the selected target:

- [Snowflake](references/SNOWFLAKE.md)
- [Databricks](references/DATABRICKS.md)
- [OMS and Airflow task translation](references/OMS.md)
