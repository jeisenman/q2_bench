# Databricks notebook source
# MAGIC %md
# MAGIC # Remote data query: pl-databricks-us-rapreprod-01
# MAGIC Generated query boilerplate. Review before running.

# COMMAND ----------

# MAGIC %run /Shared/Universal/ADLSConnections

# COMMAND ----------

from datetime import datetime, timezone
import json

from pyspark.sql import functions as F

CLIENT_ID = "f8ebcaa4-3f60-4f6e-8fa5-5b16c23032cb"
RELATIONSHIP_ID = "e031886f-4878-4e89-984a-ed46323a6aae"
HOST = "pladls2usprod.dfs.core.windows.net"
RA_FILE = "DatabaseOutput/dbStagingDeliveryToPromiseAggregates.csv"
TARGET_RUN_DATES = {"2026-09-09", "2026-10-05"}
REQUEST_WINDOWS = (
    (
        datetime(2026, 9, 8, tzinfo=timezone.utc),
        datetime(2026, 9, 12, tzinfo=timezone.utc),
    ),
    (
        datetime(2026, 10, 4, tzinfo=timezone.utc),
        datetime(2026, 10, 8, tzinfo=timezone.utc),
    ),
)
TREASURY_FIELDS = [
    "TreasuryInterestBearingBalance",
    "TreasuryInterestBearingAverageBalance",
    "TreasuryHybridBalance",
    "TreasuryHybridAverageBalance",
]
VALUE_FIELDS = [
    "RelationshipNewId",
    "RaRunId",
    "RunDate",
    "AllDepositBalance",
    "AllDepositAverageBalance",
    "ZeroInterestDepositBalance",
    "ZeroInterestDepositAverageBalance",
    "InterestBearingDepositBalance",
    "InterestBearingDepositAverageBalance",
    "TimedDepositBalance",
    "TimedDepositAverageBalance",
    "DepositTreasuryZeroInterestDemandBalance",
    "DepositTreasuryZeroInterestDemandAverageBalance",
] + TREASURY_FIELDS


def parse_timestamp(path: str, marker: str):
    value = path.rstrip("/").split(marker)[-1]
    try:
        return datetime.strptime(value[:16], "%Y-%m-%d-%H-%M").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def in_request_window(value: datetime) -> bool:
    return any(start <= value < end for start, end in REQUEST_WINDOWS)


root = f"abfss://datalake@{HOST}/ClientData/Client={CLIENT_ID}/DataIngress"
file_paths = []
for request_item in dbutils.fs.ls(root):
    request_time = parse_timestamp(request_item.path, "Request=")
    if request_time is None or not in_request_window(request_time):
        continue
    for run_item in dbutils.fs.ls(request_item.path):
        run_time = parse_timestamp(run_item.path, "RaRun=")
        if (
            run_time is None
            or run_time.strftime("%Y-%m-%d") not in TARGET_RUN_DATES
        ):
            continue
        candidate = run_item.path.rstrip("/") + "/" + RA_FILE
        try:
            items = dbutils.fs.ls(candidate)
        except Exception:
            continue
        file_paths.append(
            (
                candidate,
                request_time.isoformat(),
                run_time.isoformat(),
                sum(int(item.size) for item in items),
            )
        )

results = []
for path, request_time, run_time, size_bytes in sorted(file_paths):
    frame = (
        spark.read.option("header", True)
        .option("inferSchema", False)
        .csv(path)
    )
    columns = frame.columns
    id_column = (
        "RelationshipNewId" if "RelationshipNewId" in columns else None
    )
    target_rows = []
    if id_column:
        selected = [field for field in VALUE_FIELDS if field in columns]
        target_rows = [
            row.asDict(recursive=True)
            for row in (
                frame.where(F.lower(F.col(id_column)) == RELATIONSHIP_ID)
                .select(*selected)
                .limit(10)
                .collect()
            )
        ]
    results.append(
        {
            "path": path,
            "request_time": request_time,
            "run_time": run_time,
            "size_bytes": size_bytes,
            "header_count": len(columns),
            "header": columns,
            "missing_treasury_fields": [
                field for field in TREASURY_FIELDS if field not in columns
            ],
            "target_row_count_bounded": len(target_rows),
            "target_rows": target_rows,
        }
    )

result = {
    "client_id": CLIENT_ID,
    "relationship_id": RELATIONSHIP_ID,
    "root": root,
    "file_count": len(results),
    "files": results,
}
dbutils.notebook.exit(json.dumps(result, sort_keys=True, default=str))
