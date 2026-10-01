# Data Engineering Databricks

Use this guide to generate a read-only notebook for the production Data
Engineering Databricks workspace.

## Start from `di-pipelines`

Read the local repository root from:

```text
workspaces.data_engineering.repositories.root
```

The source checkout is:

```text
<repositories.root>/di-pipelines
```

For the default configuration this resolves to `~/ra/di-pipelines`, but never
assume that path for another developer.

Use the source tree to translate the requested DE folder or Airflow task into
the actual data location:

1. Find the DAG under `dags/precisionlender/dags/`.
2. Locate the task's `job_name` or `job_reference`.
3. Follow the reference into one of these job roots:
   - `de-jobs/src/datamart/jobs/` for Data Engineering jobs;
   - `ds-jobs/src/datascience_jobs/jobs/` for Data Science jobs;
   - `ra-jobs/src/rajobs/jobs/` only when the DAG still references it.
4. Inspect the job's context resource, dataset name, version, partition fields,
   file format, and read code.
5. Derive the folder from those declarations. Do not invent an ADLS path from
   the Python package path or Airflow task name.

Common context resources include `HistoricalDataMartADLS`,
`InternalDataMartADLS`, and `ClientDataMartADLS`. The job source determines
which one is correct.

## Build read-only notebook code

Generate the notebook with:

```json
{
  "platform": "data_engineering",
  "code": "display(dbutils.fs.ls(data_path))"
}
```

The target is `pl-databricks-us-prod-01`, so all execution must be treated as
production access. `make_databricks_notebook` wraps the supplied code as a
Databricks SOURCE notebook and returns its SHA-256 digest. After reviewing the
exact source, `run_databricks_notebook` can import and submit it to an approved
existing cluster. The generator does not prove that supplied code is read-only.

A typical bounded folder investigation is:

```python
data_path = "abfss://<container>@<account>.dfs.core.windows.net/<derived-path>"
display(dbutils.fs.ls(data_path))

data = spark.read.format("<parquet-or-delta>").load(data_path)
display(data.limit(100))
```

Keep the generated code read-only:

- list folders before selecting a partition;
- read only the required dataset and date/client partitions;
- use `limit` before display or collection;
- select only useful columns when the schema is wide;
- never call `write`, `save`, `insert`, `merge`, `delete`, `vacuum`, or
  filesystem removal or move operations.

Review the generated target and source before passing the returned digest to
`run_databricks_notebook`. The Data Engineering workspace and `de` environment
must both be enabled in `configurations.yaml`. If the task belongs to RA
preproduction rather than DE production, use
[RA_DATABRICKS.md](RA_DATABRICKS.md).
