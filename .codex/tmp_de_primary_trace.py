# Databricks notebook source
# MAGIC %md
# MAGIC # Remote data query: pl-databricks-us-prod-01
# MAGIC Generated query boilerplate. Review before running.

# COMMAND ----------

import json

from pyspark.sql import functions as F

CLIENT_ID = "f8ebcaa4-3f60-4f6e-8fa5-5b16c23032cb"
RELATIONSHIP_ID = "e031886f-4878-4e89-984a-ed46323a6aae"
HOST = "pladls2usdatamartprod.dfs.core.windows.net"
ROOT = (
    f"abfss://l3-historical@{HOST}/ClientId={CLIENT_ID}/L3/v1.0/"
    "Primary/PL_RelationshipAwareness/Relationships/"
    "RelationshipAggregateBalances/"
    f"InstancePartition={CLIENT_ID}"
)
VERSIONS = ["v1.2", "v1.3"]
DATES = ["20260909", "20261005"]
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

results = []
for version in VERSIONS:
    for date_value in DATES:
        path = (
            f"{ROOT}/VersionPartition={version}/"
            f"DatePartition={date_value}"
        )
        try:
            items = dbutils.fs.ls(path)
        except Exception as exc:
            results.append(
                {
                    "version": version,
                    "date": date_value,
                    "path": path,
                    "status": "missing_partition",
                    "error_type": type(exc).__name__,
                }
            )
            continue
        frame = (
            spark.read.option("header", True)
            .option("inferSchema", False)
            .csv(path)
        )
        columns = frame.columns
        selected = [field for field in VALUE_FIELDS if field in columns]
        target_rows = []
        if "RelationshipNewId" in columns:
            target_rows = [
                row.asDict(recursive=True)
                for row in (
                    frame.where(
                        F.lower(F.col("RelationshipNewId"))
                        == RELATIONSHIP_ID
                    )
                    .select(*selected)
                    .limit(10)
                    .collect()
                )
            ]
        results.append(
            {
                "version": version,
                "date": date_value,
                "path": path,
                "status": "found",
                "files": [
                    {"path": item.path, "size": int(item.size)}
                    for item in items
                ],
                "header_count": len(columns),
                "header": columns,
                "missing_treasury_fields": [
                    field
                    for field in TREASURY_FIELDS
                    if field not in columns
                ],
                "target_row_count_bounded": len(target_rows),
                "target_rows": target_rows,
            }
        )

dbutils.notebook.exit(
    json.dumps(
        {
            "client_id": CLIENT_ID,
            "relationship_id": RELATIONSHIP_ID,
            "root": ROOT,
            "partitions": results,
        },
        sort_keys=True,
        default=str,
    )
)
