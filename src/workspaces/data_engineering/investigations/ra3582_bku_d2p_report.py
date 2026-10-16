"""Read bounded BankUnited DV Delivery to Promise row counts on Databricks."""

# Databricks notebook source

import json
from typing import Any

dbutils: Any = globals()["dbutils"]
spark: Any = globals()["spark"]
display_fn: Any = globals().get("display")

CLIENT_ID = "f8ebcaa4-3f60-4f6e-8fa5-5b16c23032cb"
BASE_PATH = (
    "abfss://l3-historical@pladls2usdatamartprod.dfs.core.windows.net/"
    f"ClientId={CLIENT_ID}/L3/v1.0/Derived/PL_Analytics/PortfolioInsights/"
    f"DeliveryToPromiseData/InstancePartition={CLIENT_ID}/VersionPartition=v1.3/"
)

dbutils.widgets.text("date_partitions", "")
dbutils.widgets.text("max_rows", "100")
requested = [
    value.strip()
    for value in dbutils.widgets.get("date_partitions").split(",")
    if value.strip()
]
max_rows = int(dbutils.widgets.get("max_rows"))
if max_rows < 1:
    raise ValueError("max_rows must be at least 1")  # noqa: TRY003

selected = requested or ["20261003", "20261004", "20261005"]

counts = []
for date_partition in selected:
    path = f"{BASE_PATH}DatePartition={date_partition}/"
    try:
        frame = (
            spark.read.option("header", "true").option("inferSchema", "true").csv(path)
        )
        total_rows = frame.count()
        displayed_frame = frame.limit(max_rows)
        if display_fn is not None:
            display_fn(displayed_frame)
        records = [json.loads(record) for record in displayed_frame.toJSON().collect()]
        deposit_type_counts = {
            row["DepositType"] or "<null>": row["count"]
            for row in frame.groupBy("DepositType").count().collect()
        }
        counts.append(
            {
                "date_partition": date_partition,
                "rows": total_rows,
                "displayed_rows": len(records),
                "max_rows": max_rows,
                "columns": frame.columns,
                "deposit_type_counts": deposit_type_counts,
                "records": records,
            }
        )
    except Exception as error:
        counts.append(
            {"date_partition": date_partition, "error": str(error).splitlines()[0]}
        )

result = {
    "dataset": "DeliveryToPromiseData",
    "client_id": CLIENT_ID,
    "version": "v1.3",
    "date_partitions": counts,
    "total_rows": sum(item.get("rows", 0) for item in counts),
}
dbutils.notebook.exit(json.dumps(result, sort_keys=True))
