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

## Example: RA field non-null / non-zero coverage check

Use this template to check, per day, whether a set of fields in an RA run's
output CSV were populated (non-null, non-blank) and non-zero across every row.
It walks `Request=`/`RaRun=` partitions in a date window, so it does not
require a pre-resolved file list.

Resolve `{host}` and the raw source path with the "Resolve the source
repository" steps above (see also `docs/ra-run-tracing.md`). Fill in the
placeholders before passing the code to `make_databricks_notebook` with
`"platform": "ra"`; do not run it until the field list and date window have
been reviewed.

```python
from datetime import datetime, timezone
import json

from pyspark.sql import functions as F

CLIENT_ID = "{client_id}"                       # e.g. "99b9412b-70fd-4221-8431-d1b3934889ec"
START = datetime({start_year}, {start_month}, {start_day}, tzinfo=timezone.utc)
END = datetime({end_year}, {end_month}, {end_day}, tzinfo=timezone.utc)
HOST = "{host}"                                 # e.g. "pladls2usstaging.dfs.core.windows.net"
RA_FILE = "{ra_file}"                           # e.g. "DatabaseOutput/dbStagingDeliveryToPromiseAggregates.csv"
FIELDS = [
    # one or more column names to check, e.g.:
    # "TreasuryInterestBearingBalance",
    # "TreasuryInterestBearingAverageBalance",
    "{field_1}",
    "{field_2}",
]


def parse_timestamp(path, marker):
    value = path.rstrip("/").split(marker)[-1]
    try:
        return datetime.strptime(value[:16], "%Y-%m-%d-%H-%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


root = f"abfss://datalake@{{HOST}}/ClientData/Client={{CLIENT_ID}}/DataIngress"
file_paths = []
for request_item in dbutils.fs.ls(root):
    if "Request=" not in request_item.path:
        continue
    request_timestamp = parse_timestamp(request_item.path, "Request=")
    if request_timestamp is None or not (START <= request_timestamp < END):
        continue
    for run_item in dbutils.fs.ls(request_item.path):
        if "RaRun=" not in run_item.path:
            continue
        run_timestamp = parse_timestamp(run_item.path, "RaRun=")
        if run_timestamp is None or not (START <= run_timestamp < END):
            continue
        candidate = run_item.path.rstrip("/") + "/" + RA_FILE
        try:
            dbutils.fs.ls(candidate)
        except Exception:
            continue
        file_paths.append(candidate)

if not file_paths:
    dbutils.notebook.exit(json.dumps({{"client_id": CLIENT_ID, "status": "no_run_files_in_window"}}, sort_keys=True))

frame = (
    spark.read.option("header", True)
    .option("inferSchema", False)
    .csv(sorted(file_paths))
    .withColumn("_run_date", F.regexp_extract(F.input_file_name(), r"RaRun=(\d{{4}}-\d{{2}}-\d{{2}})", 1))
)
missing_fields = [field for field in FIELDS if field not in frame.columns]
if missing_fields:
    dbutils.notebook.exit(
        json.dumps(
            {{
                "client_id": CLIENT_ID,
                "status": "missing_columns",
                "missing_fields": missing_fields,
                "run_file_count": len(file_paths),
            }},
            sort_keys=True,
        )
    )

expressions = [F.count(F.lit(1)).alias("row_count")]
for field in FIELDS:
    normalized = F.trim(F.col(field))
    expressions.extend(
        [
            F.sum(F.when(F.col(field).isNotNull() & (normalized != ""), 1).otherwise(0)).alias(f"{{field}}__non_null"),
            F.sum(F.when(F.col(field).cast("double") != 0.0, 1).otherwise(0)).alias(f"{{field}}__non_zero"),
        ]
    )

rows = frame.groupBy("_run_date").agg(*expressions).orderBy("_run_date").collect()
daily = []
for row in rows:
    values = row.asDict()
    row_count = int(values["row_count"])
    fields = {{}}
    for field in FIELDS:
        non_null_count = int(values[f"{{field}}__non_null"] or 0)
        non_zero_count = int(values[f"{{field}}__non_zero"] or 0)
        fields[field] = {{
            "non_null_count": non_null_count,
            "non_zero_count": non_zero_count,
            "all_rows_non_null": non_null_count == row_count,
            "all_rows_non_zero": non_zero_count == row_count,
        }}
    daily.append(
        {{
            "run_date": values["_run_date"],
            "row_count": row_count,
            "all_fields_non_null_for_all_rows": all(item["all_rows_non_null"] for item in fields.values()),
            "all_fields_non_zero_for_all_rows": all(item["all_rows_non_zero"] for item in fields.values()),
            "fields": fields,
        }}
    )

result = {{
    "client_id": CLIENT_ID,
    "window_start": START.isoformat(),
    "window_end_exclusive": END.isoformat(),
    "run_file_count": len(file_paths),
    "days_all_fields_non_null": [item["run_date"] for item in daily if item["all_fields_non_null_for_all_rows"]],
    "days_all_fields_non_zero": [item["run_date"] for item in daily if item["all_fields_non_zero_for_all_rows"]],
    "daily": daily,
}}

dbutils.notebook.exit(json.dumps(result, sort_keys=True))
```

This returns aggregate counts and day-level booleans only, never raw rows, so
it stays within the read-only, bounded-evidence rule above.

