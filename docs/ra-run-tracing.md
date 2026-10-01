# Tracing an RA run in Databricks

Reviewed: 2026-10-01

Use this procedure to locate and inspect the raw files produced by a
Relationship Awareness (RA) run. It keeps execution in RA Databricks, reads
only pinned clients and dates, and returns aggregate evidence rather than
production rows.

## 1. Derive the path from the active job

Do not infer an ADLS path from a package or task name. Resolve the repository
root from `workspaces.data_engineering.repositories.root`, then inspect the
active DAG in `<repositories.root>/di-pipelines`.

For example:

```bash
cd <repositories.root>/di-pipelines
rg -n -C 12 "RelationshipAggregateBalances" \
  dags/precisionlender/dags/task_groups/main/ra_jobs.py
```

The active `get_relationship_aggregate_balances` task declares:

```text
job_reference:
  datamart.jobs.ra.relationship_aggregate_balances.to_datamart.RelationshipAggregateBalances
inputResource:
  OperationalADLS
inputPathConvention:
  di_pyjobs.path.relationship_awareness.OperationalRA
raFile:
  DatabaseOutput/dbStagingDeliveryToPromiseAggregates.csv
fileFormat:
  csv
```

Follow `job_reference` to verify the expected CSV contract:

```text
de-jobs/src/datamart/jobs/ra/relationship_aggregate_balances/to_datamart.py
```

Then inspect `OperationalRA` in the `di-pyjobs` checkout. Its path contract is:

```text
filesystem: datalake
/ClientData/Client={client_id}/DataIngress/
  Request={request_time}/RaRun={run_time}/{filename}
```

The resulting RelationshipAggregateBalances source path is:

```text
abfss://datalake@{operational_account}.dfs.core.windows.net/
  ClientData/Client={client_id}/DataIngress/
  Request={YYYY-MM-DD-HH-MM}/RaRun={YYYY-MM-DD-HH-MM}/
  DatabaseOutput/dbStagingDeliveryToPromiseAggregates.csv
```

This is the raw operational source. The `HistoricalDataMartADLS`
`DataStudioHistorical` path is the ingestion sink and is not the correct
starting point when tracing the original RA run.

## 2. Resolve clients and the operational account

For Alpha, inspect:

```text
<repositories.root>/di-scheduling/Deployment/ContxMetadata/alpha/
```

List active PrecisionLender partitions:

```bash
jq '.ApplicationPartitionsMetadata[]
  | select(.is_active == true and .application == "precisionlender")
  | {name, client_group, shared_group, is_data_isolated}' \
  application_partitions.json
```

Resolve `OperationalADLS` using the selected partition's client or shared
group:

```bash
jq '.DatastoresMetadata.instances[]
  | select(.kind == "OperationalADLS")
  | {name, groups, host_name, domain}' datastores.json
```

At the time of review, Alpha resolves to:

```text
pladls2usstaging.dfs.core.windows.net
```

Always re-read metadata rather than treating that account as permanent.

## 3. Use session-scoped OAuth

The RA workspace contains:

```text
/Shared/Universal/ADLSConnections
```

Run it at the beginning of the investigation notebook:

```python
# MAGIC %run /Shared/Universal/ADLSConnections
```

It reads `ADLSID`, `ADLSKey`, and `ADLSTenant` from the existing
`AdminScope` secret scope and configures Spark OAuth for the notebook session.
It does not install a package or change the cluster's attached libraries.
Never copy secret values into notebook source or output.

## 4. Run a bounded daily field check

Pin the client, UTC window, file, and fields. The following notebook finds
concrete RA files and reports daily non-null and non-zero counts without
returning source rows:

```python
# MAGIC %run /Shared/Universal/ADLSConnections

# COMMAND ----------

from datetime import datetime, timezone
import json

from pyspark.sql import functions as F

CLIENT_ID = "<client-id>"
START = datetime(2026, 9, 1, tzinfo=timezone.utc)
END = datetime(2026, 10, 1, tzinfo=timezone.utc)
HOST = "<operational-account>.dfs.core.windows.net"
RA_FILE = "DatabaseOutput/dbStagingDeliveryToPromiseAggregates.csv"
FIELDS = [
    "TreasuryInterestBearingBalance",
    "TreasuryInterestBearingAverageBalance",
    "TreasuryHybridBalance",
    "TreasuryHybridAverageBalance",
]


def parse_timestamp(path: str, marker: str) -> datetime | None:
    value = path.rstrip("/").split(marker)[-1]
    try:
        parsed = datetime.strptime(value[:16], "%Y-%m-%d-%H-%M")
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc)


root = f"abfss://datalake@{HOST}/ClientData/Client={CLIENT_ID}/DataIngress"
file_paths: list[str] = []

for request_item in dbutils.fs.ls(root):
    request_time = parse_timestamp(request_item.path, "Request=")
    if request_time is None or not START <= request_time < END:
        continue
    for run_item in dbutils.fs.ls(request_item.path):
        run_time = parse_timestamp(run_item.path, "RaRun=")
        if run_time is None or not START <= run_time < END:
            continue
        candidate = run_item.path.rstrip("/") + "/" + RA_FILE
        try:
            dbutils.fs.ls(candidate)
        except Exception:
            continue
        file_paths.append(candidate)

if not file_paths:
    dbutils.notebook.exit(json.dumps({"status": "no_run_files"}))

frame = (
    spark.read.option("header", True)
    .option("inferSchema", False)
    .csv(sorted(file_paths))
    .withColumn(
        "_run_date",
        F.regexp_extract(
            F.input_file_name(),
            r"RaRun=(\d{4}-\d{2}-\d{2})",
            1,
        ),
    )
)

missing_fields = [field for field in FIELDS if field not in frame.columns]
if missing_fields:
    dbutils.notebook.exit(
        json.dumps(
            {
                "status": "missing_columns",
                "missing_fields": missing_fields,
                "run_file_count": len(file_paths),
            },
            sort_keys=True,
        )
    )

aggregates = [F.count(F.lit(1)).alias("row_count")]
for field in FIELDS:
    populated = F.col(field).isNotNull() & (F.trim(F.col(field)) != "")
    aggregates.extend(
        [
            F.sum(F.when(populated, 1).otherwise(0)).alias(f"{field}__non_null"),
            F.sum(F.when(F.col(field).cast("double") != 0.0, 1).otherwise(0)).alias(
                f"{field}__non_zero"
            ),
        ]
    )

daily = [
    row.asDict()
    for row in (
        frame.groupBy("_run_date").agg(*aggregates).orderBy("_run_date").collect()
    )
]

dbutils.notebook.exit(
    json.dumps(
        {
            "client_id": CLIENT_ID,
            "run_file_count": len(file_paths),
            "daily": daily,
        },
        sort_keys=True,
    )
)
```

Compare each field count with `row_count`:

- `non_null == row_count`: every row has a populated value.
- `non_zero == row_count`: every row has a non-zero numeric value.
- Multiple RA files can occur on one date; grouping by `_run_date` combines
  those runs for a daily answer.

## 5. Generate, submit, and retrieve output

Preferred workflow:

1. Call `make_databricks_notebook` with `platform="ra"`.
2. Review the complete returned SOURCE and retain `source_sha256`.
3. Call `run_databricks_notebook` with the exact source, digest, and an
   approved existing cluster ID.

If the MCP submission endpoint is unavailable, use the native Databricks CLI
with the exact reviewed source:

```bash
set -a
source .env
set +a
export DATABRICKS_HOST="$RA_DATABRICKS_HOST"
export DATABRICKS_TOKEN="$RA_DATABRICKS_TOKEN"

shasum -a 256 /tmp/ra_trace.py

databricks workspace import \
  /Shared/remote-data-mcp/ra/<source-sha256> \
  --file /tmp/ra_trace.py \
  --format SOURCE \
  --language PYTHON \
  --overwrite

databricks jobs submit --no-wait --json '{
  "run_name": "remote-data-ra-trace",
  "tasks": [{
    "task_key": "query",
    "existing_cluster_id": "<approved-cluster-id>",
    "notebook_task": {
      "notebook_path": "/Shared/remote-data-mcp/ra/<source-sha256>"
    },
    "timeout_seconds": 1200
  }],
  "timeout_seconds": 1200
}'
```

Save the parent run ID, then obtain the task run ID:

```bash
databricks jobs get-run <parent-run-id> --output json \
  | jq '{state: .state, task_run_id: .tasks[0].run_id}'
```

Retrieve the bounded notebook result using the task run ID:

```bash
databricks jobs get-run-output <task-run-id> --output json \
  | jq -r '.notebook_output.result' \
  | jq .
```

## Failure interpretation

- `Invalid configuration value ... fs.azure.account.key`: OAuth was not
  initialized for the notebook session.
- `PathNotFound` at `DataIngress`: the client has no directory at that
  operational location; do not report this as zero rows.
- `no_run_files`: the client directory exists, but no matching file was found
  in the pinned window.
- `missing_columns`: the file schema predates the fields or differs between
  runs. Inspect each file's header independently before concluding that every
  run lacks the fields.
- A successful parent run does not contain notebook output directly. Use the
  task run ID with `jobs get-run-output`.

