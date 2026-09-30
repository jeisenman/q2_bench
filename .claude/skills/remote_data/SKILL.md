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
3. Use `make_adls_notebook` for bounded reads from dev, staging, US production,
   or CA production ADLS.
4. Use `make_snowflake_notebook` for bounded read-only SQL. It defaults to
   `prod_us`; pass `alpha` or `staging` only when the user explicitly requests
   another environment.
5. Use `query_oms` or `query_job_evidence` only for raw OMS evidence from
   `pl-oms-us-primary` or `pl-oms-ca-primary`.
6. Review generated notebook source before running it in a remote workspace.

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
- [Data Engineering Databricks](references/DE_DATABRICKS.md)
- [RA Databricks](references/RA_DATABRICKS.md)
- [OMS and Airflow task translation](references/OMS.md)
