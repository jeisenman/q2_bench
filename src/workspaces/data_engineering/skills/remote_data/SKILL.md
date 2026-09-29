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
4. Use `make_snowflake_notebook` for bounded read-only SQL.
5. Use `query_oms` or `query_job_evidence` only for raw OMS evidence from
   `pl-oms-us-primary` or `pl-oms-ca-primary`.
6. Review generated notebook source before running it in a remote workspace.

OMS classification belongs to production-support logic, not this skill.
