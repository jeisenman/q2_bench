# RA Databricks

Use this guide to generate a read-only notebook for the RA preproduction
Databricks workspace.

## Find the RA implementation

Resolve `<repositories.root>` from
`workspaces.data_engineering.repositories.root`, then inspect:

```text
<repositories.root>/di-pipelines
```

Prefer these locations:

- `de-jobs/src/datamart/jobs/ra/` for current RA ingestion and transformation
  jobs;
- `dags/precisionlender/dags/task_groups/` and the parent DAG for task
  composition and dependencies;
- `ra-jobs/src/rajobs/jobs/` only when an active DAG references legacy RA job
  code;
- `de-jobs/src/datamart/jobs/common/` for shared path conventions.

Follow the DAG's `job_reference` and inspect the selected job's context
resource, dataset name, version, partition fields, and file format. Preserve
exact task-group prefixes such as `ra_group.` when searching for the task.

## Generate the notebook

Call:

```json
{
  "platform": "ra",
  "code": "display(dbutils.fs.ls(data_path))"
}
```

The target is RA preproduction workspace
`pl-databricks-us-rapreprod-01`. It has no registered SQL warehouse, so use
Spark and filesystem APIs rather than assuming a SQL warehouse is available.

A bounded inspection can list the derived folder and preview its contents:

```python
data_path = "abfss://<container>@<account>.dfs.core.windows.net/<derived-path>"
display(dbutils.fs.ls(data_path))

data = spark.read.format("<csv-or-parquet>").load(data_path)
display(data.limit(100))
```

The notebook generator accepts arbitrary Python code. Keep it read-only and
review it before passing the returned digest and an approved existing cluster
ID to `run_databricks_notebook`:

- scope reads to one client, dataset, version, and date where possible;
- specify CSV options found in the source job instead of relying on inference;
- do not write tables or files;
- do not repair, vacuum, optimize, move, or delete data;
- do not reuse DE production paths merely because the package names match.

For the production Data Engineering workspace, use
[DE_DATABRICKS.md](DE_DATABRICKS.md).
