"""Temporary read-only Databricks probe for Truist DV Baird DTP rows."""

# Databricks notebook source

import json
from typing import Any

dbutils: Any = globals()["dbutils"]
spark: Any = globals()["spark"]

CLIENT_ID = "c3563e8a-3e29-45e9-9dad-9e6743126d78"
BASE_PATH = (
    "abfss://l3-historical@pladls2usdatamartprod.dfs.core.windows.net/"
    f"ClientId={CLIENT_ID}/L3/v1.0/Derived/PL_Analytics/PortfolioInsights/"
    f"DeliveryToPromiseData/InstancePartition={CLIENT_ID}/VersionPartition=v1.3/"
)

result: dict[str, Any] = {
    "client_id": CLIENT_ID,
    "base_path": BASE_PATH,
    "status": "started",
}

try:
    partition_items = [
        item
        for item in dbutils.fs.ls(BASE_PATH)
        if "DatePartition=" in item.path
    ]
except Exception as error:
    result.update({"status": "path_error", "error": str(error)[:1000]})
    dbutils.notebook.exit(json.dumps(result, sort_keys=True))

partitions = sorted(
    partition_items,
    key=lambda item: item.path.rsplit("DatePartition=", 1)[-1].strip("/"),
    reverse=True,
)[:20]
result["partitions"] = [item.path for item in partitions]
records: list[dict[str, Any]] = []

for partition in partitions:
    try:
        frame = (
            spark.read.option("header", "true")
            .option("inferSchema", "false")
            .csv(partition.path)
        )
        name_columns = [
            column
            for column in (
                "RelationshipName",
                "Name",
                "Relationship",
                "relationship_name",
            )
            if column in frame.columns
        ]
        if not name_columns:
            records.append(
                {
                    "partition": partition.path,
                    "status": "name_column_not_found",
                    "columns": frame.columns,
                }
            )
            continue
        name_column = name_columns[0]
        selected = [
            column
            for column in (
                "DatePartition",
                "RelationshipGuid",
                "RelationshipId",
                "RelationshipName",
                "Name",
                "Relationship",
                "DepositType",
                "CurrentBalance",
                "LastCoreBalancePerDepositType",
                "LastCoreBalanceAllDeposits",
                "StartingBalance",
                "MissingBalance",
                "TargetDeposit",
                "DaysSinceLastCoreBalance",
                "ProductName",
                "OriginationChannel",
                "ServicingChannel",
                "RiskRating",
                "FacilityRating",
                "RemainingAmortizationTerm",
                "RemainingExpectedLife",
            )
            if column in frame.columns
        ]
        matches = (
            frame.filter(frame[name_column].isNotNull())
            .filter(frame[name_column].contains("BAIRD"))
            .select(*selected)
            .limit(100)
            .collect()
        )
        if matches:
            records.extend(
                {
                    "partition": partition.path,
                    "name_column": name_column,
                    "row": row.asDict(recursive=True),
                }
                for row in matches
            )
        else:
            records.append(
                {
                    "partition": partition.path,
                    "name_column": name_column,
                    "status": "no_baird_match",
                    "columns": frame.columns,
                }
            )
    except Exception as error:
        records.append(
            {"partition": partition.path, "status": "read_error", "error": str(error).splitlines()[0]}
        )

result.update({"status": "ok", "records": records})
dbutils.notebook.exit(json.dumps(result, default=str, sort_keys=True))
