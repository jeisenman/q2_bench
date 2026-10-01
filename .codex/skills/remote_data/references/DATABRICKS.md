# Databricks

Use this guide to generate a read-only notebook for an approved Databricks
workspace. Select the target from the request, the Airflow task, or
`list_remote_data_targets` before generating notebook code.

## Resolve the source repository

Read the local repository root from:

```text
workspaces.data_engineering.repositories.root
```

The source checkout is:

```text
<repositories.root>/di-pipelines
```

Never assume the default path for another developer.

For a requested Airflow task or data folder:

1. Find the DAG under `dags/precisionlender/dags/`.
2. Locate the task's `job_name` or `job_reference`.
3. Follow the reference into the relevant job root:
   - `de-jobs/src/datamart/jobs/` for Data Engineering jobs;
   - `ds-jobs/src/datascience_jobs/jobs/` for Data Science jobs;
   - `de-jobs/src/datamart/jobs/ra/` for current RA jobs;
   - `ra-jobs/src/rajobs/jobs/` only when an active DAG still references legacy
     RA code;
   - `dags/precisionlender/dags/task_groups/` and the parent DAG when resolving
     RA task composition;
   - `de-jobs/src/datamart/jobs/common/` for shared path conventions.
4. Inspect the selected job's context resource, dataset name, version,
   partition fields, file format, and read code.
5. Derive the folder from those declarations. Do not invent an ADLS path from
   the Python package path or Airflow task name.

Common context resources include `HistoricalDataMartADLS`,
`InternalDataMartADLS`, and `ClientDataMartADLS`. The job source determines
which one is correct. Preserve exact task-group prefixes such as `ra_group.`
when searching for RA tasks.

## Select the Databricks target

### Data Engineering production

Use:

```json
{
  "platform": "data_engineering",
  "code": "display(dbutils.fs.ls(data_path))"
}
```

The target is `pl-databricks-us-prod-01`, so all execution is production
access. The Data Engineering workspace and `de` environment must both be
enabled in `configurations.yaml`.

### RA preproduction

Use:

```json
{
  "platform": "ra",
  "code": "display(dbutils.fs.ls(data_path))"
}
```

The target is `pl-databricks-us-rapreprod-01`. It has no registered SQL
warehouse, so use Spark and filesystem APIs rather than assuming a SQL
warehouse is available.

Scope reads to one client, dataset, version, and date where possible. Specify
CSV options found in the source job instead of relying on inference. Do not
reuse DE production paths merely because package names match.

## Build and run the notebook

Call `make_databricks_notebook` with the selected platform and reviewed code.
The tool wraps the code as a Databricks SOURCE notebook and returns its
`source_sha256`. The generator does not prove that supplied code is read-only.

A typical bounded folder investigation is:

```python
data_path = "abfss://<container>@<account>.dfs.core.windows.net/<derived-path>"
display(dbutils.fs.ls(data_path))

data = spark.read.format("<csv-or-parquet>").load(data_path)
display(data.limit(100))
```

Review the exact returned source, target, and digest before calling
`run_databricks_notebook` with the digest and an approved existing cluster ID.
The tool returns after the one-time run is submitted.

Keep generated code read-only:

- list folders before selecting a partition;
- read only the required dataset and date or client partitions;
- use `limit` before display or collection;
- select only useful columns when the schema is wide;
- never call `write`, `save`, `insert`, `merge`, `delete`, `vacuum`, or
  filesystem removal or move operations.

