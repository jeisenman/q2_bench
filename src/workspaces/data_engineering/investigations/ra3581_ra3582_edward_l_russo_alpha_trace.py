# Databricks notebook source
# MAGIC %md
# MAGIC # RA-3581/RA-3582: EDWARD L RUSSO Alpha lineage
# MAGIC
# MAGIC Imports the RA-3582 Alpha archive, reads the Alpha downstream datasets,
# MAGIC and records where the target relationship stops reaching D2P.
# COMMAND ----------
import json
import sys
from typing import Any
from pyspark.sql import DataFrame, functions as F
CLIENT_ID = "f8ebcaa4-3f60-4f6e-8fa5-5b16c23032cb"
RUN_DATE = "20261005"
RUN_TIME = "20261005-050000"
TARGET_NAME = "EDWARD L RUSSO"
ALPHA_ARCHIVE = "/dbfs/FileStore/jars/000_datascience_jobs-RA-3582.zip"
DI_PYJOBS_ARCHIVE = "/dbfs/FileStore/jars/di_pyjobs-source.zip"
HISTORICAL_ROOT = (
    "abfss://l3-historical@pladls2usdatamartprod.dfs.core.windows.net"
)
BASE = f"{HISTORICAL_ROOT}/ClientId={CLIENT_ID}/L3/v1.0"
JOB_MODULE = "datascience_jobs.jobs.data.delivery_to_promise.delivery_to_promise_data"
# COMMAND ----------
# COMMAND ----------
for dbfs_path, local_path in [
    ("dbfs:/FileStore/jars/000_datascience_jobs-RA-3582.zip", ALPHA_ARCHIVE),
    ("dbfs:/FileStore/jars/di_pyjobs-source.zip", DI_PYJOBS_ARCHIVE),
]:
    try:
        dbutils.fs.ls(dbfs_path)
    except Exception as error:
        raise FileNotFoundError(f"Required DBFS archive is missing: {dbfs_path}") from error
    if local_path not in sys.path:
        sys.path.insert(0, local_path)
import types
snowflake = types.ModuleType("snowflake")
connector = types.ModuleType("snowflake.connector")
connection = types.ModuleType("snowflake.connector.connection")
cursor = types.ModuleType("snowflake.connector.cursor")
errors = types.ModuleType("snowflake.connector.errors")
connection.SnowflakeConnection = object
cursor.SnowflakeCursor = object
errors.ProgrammingError = Exception
connector.connection = connection
connector.cursor = cursor
connector.errors = errors
connector.connect = lambda **_: None
snowflake.connector = connector
sys.modules.update({
    "snowflake": snowflake,
    "snowflake.connector": connector,
    "snowflake.connector.connection": connection,
    "snowflake.connector.cursor": cursor,
    "snowflake.connector.errors": errors,
})
sqlalchemy = types.ModuleType("sqlalchemy")
sqlalchemy.__version__ = "2.0.0"
sqlalchemy_engine = types.ModuleType("sqlalchemy.engine")
sqlalchemy_engine.Engine = object
sqlalchemy.engine = sqlalchemy_engine
sqlalchemy_sql = types.ModuleType("sqlalchemy.sql")
sqlalchemy_sql.text = lambda query: query
sqlalchemy_sql.func = types.SimpleNamespace(now=lambda: None)
sqlalchemy.sql = sqlalchemy_sql
sqlalchemy_exc = types.ModuleType("sqlalchemy.exc")
for exception_name in [
    "ProgrammingError",
    "NoSuchTableError",
    "NoSuchColumnError",
    "OperationalError",
]:
    setattr(sqlalchemy_exc, exception_name, Exception)
sqlalchemy.exc = sqlalchemy_exc
sqlalchemy.create_engine = lambda *args, **kwargs: None
sys.modules.update({
    "sqlalchemy": sqlalchemy,
    "sqlalchemy.engine": sqlalchemy_engine,
    "sqlalchemy.sql": sqlalchemy_sql,
    "sqlalchemy.exc": sqlalchemy_exc,
})
SqlAlchemyPlaceholder = type(
    "SqlAlchemyPlaceholder",
    (),
    {"__init__": lambda self, *args, **kwargs: None,
     "with_variant": lambda self, *args, **kwargs: self},
)
sqlalchemy_column = lambda *args, **kwargs: SqlAlchemyPlaceholder()
sqlalchemy_declarative_base = lambda: type(
    "Base", (), {"metadata": types.SimpleNamespace(create_all=lambda *_args, **_kwargs: None)}
)
sqlalchemy.BigInteger = SqlAlchemyPlaceholder
sqlalchemy.Column = sqlalchemy_column
sqlalchemy.DateTime = SqlAlchemyPlaceholder
sqlalchemy.Enum = SqlAlchemyPlaceholder
sqlalchemy.Integer = SqlAlchemyPlaceholder
sqlalchemy.Sequence = SqlAlchemyPlaceholder
sqlalchemy.String = SqlAlchemyPlaceholder
sqlalchemy.Text = SqlAlchemyPlaceholder
sqlalchemy.select = lambda *args, **kwargs: SqlAlchemyPlaceholder()
sqlalchemy_orm = types.ModuleType("sqlalchemy.orm")
sqlalchemy_orm.declarative_base = sqlalchemy_declarative_base
sqlalchemy_orm.Session = SqlAlchemyPlaceholder
sqlalchemy.orm = sqlalchemy_orm
sys.modules["sqlalchemy.orm"] = sqlalchemy_orm
dimodels = types.ModuleType("dimodels")
dimodels_client = types.ModuleType("dimodels.client")
dimodels_client.ModelServerClient = type("ModelServerClient", (), {})
dimodels.client = dimodels_client
sys.modules.update({"dimodels": dimodels, "dimodels.client": dimodels_client})
import datascience_jobs.jobs.data.delivery_to_promise.delivery_to_promise_data as job
def version_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.removeprefix("v").split("."))
def dataset_root(stage: str, provider: str, group: str, dataset: str) -> str:
    return f"{BASE}/{stage}/{provider}/{group}/{dataset}/InstancePartition={CLIENT_ID}"
def discover_partitions(
    root: str, partition_name: str, max_partition: str
) -> tuple[str, list[str]]:
    versions = [
        item
        for item in dbutils.fs.ls(root)
        if item.name.rstrip("/").startswith("VersionPartition=")
    ]
    if not versions:
        raise FileNotFoundError(f"No versions found below {root}")
    version = max(
        (item.name.rstrip("/").split("=", 1)[1] for item in versions),
        key=version_key,
    )
    version_root = f"{root}/VersionPartition={version}"
    partitions = []
    for item in dbutils.fs.ls(version_root):
        name = item.name.rstrip("/")
        if not name.startswith(f"{partition_name}="):
            continue
        value = name.split("=", 1)[1]
        if value <= max_partition:
            partitions.append(item.path.rstrip("/"))
    if not partitions:
        raise FileNotFoundError(
            f"No {partition_name} partitions <= {max_partition} below {version_root}"
        )
    return version, sorted(partitions)
def read_dataset(
    stage: str,
    provider: str,
    group: str,
    dataset: str,
    file_format: str,
    partition_name: str = "DatePartition",
    max_partition: str = RUN_DATE,
) -> tuple[DataFrame, dict[str, Any]]:
    root = dataset_root(stage, provider, group, dataset)
    version, paths = discover_partitions(root, partition_name, max_partition)
    reader = spark.read.option("basePath", root)
    if file_format == "csv":
        reader = reader.option("header", "true").option("inferSchema", "true")
    frame = reader.format(file_format).load(paths)
    return frame, {
        "dataset": dataset,
        "version": version,
        "partition_name": partition_name,
        "partition_count": len(paths),
        "first_partition": paths[0].rsplit("/", 1)[-1],
        "last_partition": paths[-1].rsplit("/", 1)[-1],
    }
def exact_name(column: str) -> F.Column:
    return F.upper(
        F.trim(F.regexp_replace(F.coalesce(F.col(column), F.lit("")), r"\s+", " "))
    )
def first_present(frame: DataFrame, candidates: list[str]) -> str | None:
    return next((column for column in candidates if column in frame.columns), None)
def count_rows(frame: DataFrame) -> int:
    return frame.limit(1000000).count()
def rows(frame: DataFrame, columns: list[str], limit: int = 100) -> list[dict]:
    selected = [column for column in columns if column in frame.columns]
    return [row.asDict(recursive=True) for row in frame.select(*selected).limit(limit).collect()]
# COMMAND ----------
account_level_raw, account_meta = read_dataset(
    "Derived", "PL_Application", "Opportunities", "AccountLevelOpportunitiesSnapshot",
    "parquet", "WriteTimePartition", RUN_TIME
)
relationship_aggregate_raw, aggregate_meta = read_dataset(
    "Primary", "PL_RelationshipAwareness", "Relationships",
    "RelationshipAggregateBalances", "csv"
)
relationships_raw, relationships_meta = read_dataset(
    "Derived", "PL_RelationshipAwareness", "Relationships", "Relationships", "parquet"
)
users_raw, users_meta = read_dataset(
    "Primary", "PL_Application", "Users", "Users", "csv"
)
regions_raw, regions_meta = read_dataset(
    "Primary", "PL_Application", "Regions", "Regions", "csv"
)
d2p_raw, d2p_meta = read_dataset(
    "Derived", "PL_Analytics", "PortfolioInsights", "DeliveryToPromiseData", "csv"
)
account_level_raw = account_level_raw.filter(F.col("WriteTimePartition") == RUN_TIME)
d2p_raw = d2p_raw.filter(F.col("DatePartition") == RUN_DATE)
relationship_name_column = first_present(relationships_raw, ["Name", "RelationshipName"])
if relationship_name_column is None:
    raise AssertionError(
        f"Relationship name column was not found; columns={relationships_raw.columns}"
    )
relationship_target = relationships_raw.filter(
    exact_name(relationship_name_column) == F.lit(TARGET_NAME)
)
relationship_id_column = first_present(relationship_target, ["Id", "RelationshipId"])
aggregate_id_column = first_present(
    relationship_aggregate_raw, ["RelationshipNewId", "RelationshipId", "Id"]
)
if relationship_id_column is None or aggregate_id_column is None:
    raise AssertionError("Relationship ID columns were not found.")
target_ids = [
    row[0]
    for row in relationship_target.select(relationship_id_column)
    .where(F.col(relationship_id_column).isNotNull())
    .distinct()
    .collect()
]
aggregate_name_column = first_present(relationship_aggregate_raw, ["Name", "RelationshipName"])
if aggregate_name_column is not None:
    aggregate_target = relationship_aggregate_raw.filter(
        exact_name(aggregate_name_column) == F.lit(TARGET_NAME)
    )
else:
    aggregate_target = relationship_aggregate_raw.filter(
        F.col(aggregate_id_column).isin(target_ids)
    )
target_ids.extend(
    row[0]
    for row in aggregate_target.select(aggregate_id_column)
    .where(F.col(aggregate_id_column).isNotNull())
    .distinct()
    .collect()
)
target_ids = sorted({value for value in target_ids if value})
if not target_ids:
    raise AssertionError(f"{TARGET_NAME} was not found in Alpha source datasets.")
account_relationship_column = first_present(
    account_level_raw, ["RelationshipId", "RelationshipGuid"]
)
if account_relationship_column is None:
    raise AssertionError("Account opportunity relationship key was not found.")
target_account_raw = account_level_raw.filter(
    F.col(account_relationship_column).isin(target_ids)
)
target_d2p = d2p_raw.filter(F.col("RelationshipGuid").isin(target_ids))
# COMMAND ----------
account_level_filtered = job.filter_account_level(
    account_level_raw, RUN_DATE, job.LOOKBACK_DAYS
)
target_account_filtered = account_level_filtered.filter(
    F.col(account_relationship_column).isin(target_ids)
)
opps_selected = job.dh.select_and_rename_columns(
    account_level_filtered, job.OPPORTUNITY_COLUMNS
)
opps_prepped = job.dh.get_largest_entry_by_value(
    opps_selected, ["OpportunityId"], "OppDepositsPromisedAllTypes", F.row_number
)
target_opps_prepped = opps_prepped.filter(
    F.col("RelationshipGuid").isin(target_ids)
)
deposits = job.get_deposit_account_data(account_level_filtered, job.ACCOUNT_COLUMNS)
opps_type_level = job.add_deposits_promised_by_type(opps_prepped, deposits)
target_opps_type_level = opps_type_level.filter(
    F.col("RelationshipGuid").isin(target_ids)
)
aggregate_selected = job.dh.select_and_rename_columns(
    relationship_aggregate_raw, job.REL_AGG_BALANCES_COLS
)
aggregate_long = job.convert_to_long_format(aggregate_selected)
aggregate_positive = aggregate_long.filter(F.col("Balance") > 0)
aggregate_latest = job.dh.get_latest_entry_by_date(
    aggregate_positive, ["RelationshipGuid", "DepositType"], "DatePartition", F.rank
)
target_aggregate_positive = aggregate_positive.filter(
    F.col("RelationshipGuid").isin(target_ids)
)
target_aggregate_latest = aggregate_latest.filter(
    F.col("RelationshipGuid").isin(target_ids)
)
relationships_latest = job.dh.get_latest_entry_by_date(
    relationships_raw, ["RelationshipId"], "DatePartition", F.row_number
)
ra_data = job.dh.select_and_rename_columns(
    relationships_latest, job.RELATIONSHIPS_COLS
)
aggregate_output = job.add_summary_columns_to_core_deposits(aggregate_latest).filter(
    F.col("LastCoreBalancePerDepositType") > 0
)
target_aggregate_output = aggregate_output.filter(
    F.col("RelationshipGuid").isin(target_ids)
)
users = job.dh.get_latest_entry_by_date(users_raw, ["UserId"], "DatePartition", F.row_number)
regions = job.dh.get_latest_entry_by_date(regions_raw, ["RegionId"], "DatePartition", F.row_number)
users_regions = job.dh.select_and_rename_columns(users, job.USER_COLS).join(
    job.dh.select_and_rename_columns(regions, job.REGION_COLS),
    on="RegionId", how="inner"
).drop("RegionId")
opps_final = opps_type_level.join(users_regions, on="OwnerId", how="left")
opps_final = opps_final.join(ra_data, on="RelationshipGuid", how="left")
target_after_relationship_join = opps_final.filter(
    F.col("RelationshipGuid").isin(target_ids)
)
target_after_type_join = target_after_relationship_join.join(
    aggregate_output, on=["RelationshipGuid", "DepositType"], how="left"
)
target_account_days = target_account_raw.withColumn(
    "_close_date", F.to_date(F.col("CloseDate").cast("string"))
).withColumn(
    "_days_since_close",
    F.datediff(F.to_date(F.lit(RUN_DATE), "yyyyMMdd"), F.col("_close_date")),
)
eligibility_steps = [
    ("positive_opportunity_value", (F.col("OpportunityOtherIncome") > 0) | (F.col("OpportunityDepositAverageBalance") > 0)),
    ("closed_won", F.col("OpportunityStageStatus") == "ClosedWon"),
    ("not_deleted", ~F.col("OpportunityIsDeleted")),
    ("pipeline_scenario", F.col("ScenarioType") == "Pipeline"),
    ("has_relationship", F.col(account_relationship_column).isNotNull()),
    ("close_date_in_lookback", (F.col("_days_since_close") < job.LOOKBACK_DAYS) & (F.col("_days_since_close") >= 0)),
]
eligibility_counts = {}
eligibility_frame = target_account_days
for name, predicate in eligibility_steps:
    eligibility_frame = eligibility_frame.filter(predicate)
    eligibility_counts[name] = count_rows(eligibility_frame)
stage_counts = {
    "relationship_dimension": count_rows(relationship_target),
    "relationship_aggregate_named": count_rows(aggregate_target),
    "account_level_raw": count_rows(target_account_raw),
    "account_level_after_eligibility_filter": count_rows(target_account_filtered),
    "opportunity_after_dedup": count_rows(target_opps_prepped),
    "opportunity_deposit_type_rows": count_rows(target_opps_type_level),
    "positive_ra_type_rows": count_rows(target_aggregate_positive),
    "latest_positive_ra_type_rows": count_rows(target_aggregate_latest),
    "latest_positive_ra_summary_rows": count_rows(target_aggregate_output),
    "after_relationship_join": count_rows(target_after_relationship_join),
    "after_relationship_and_type_join": count_rows(target_after_type_join),
    "delivery_to_promise_data": count_rows(target_d2p),
}
ordered_stages = [
    "account_level_after_eligibility_filter",
    "opportunity_after_dedup",
    "opportunity_deposit_type_rows",
    "latest_positive_ra_type_rows",
    "after_relationship_join",
    "after_relationship_and_type_join",
    "delivery_to_promise_data",
]
first_loss_stage = next((name for name in ordered_stages if stage_counts[name] == 0), None)
# COMMAND ----------
result = {
    "status": "completed",
    "alpha_archive": "000_datascience_jobs-RA-3582.zip",
    "client_id": CLIENT_ID,
    "run_date": RUN_DATE,
    "target_name": TARGET_NAME,
    "target_relationship_ids": target_ids,
    "dataset_evidence": [account_meta, aggregate_meta, relationships_meta, users_meta, regions_meta, d2p_meta],
    "ra3581_treasury_fields_present": {
        field: field in relationship_aggregate_raw.columns
        for field in [
            "TreasuryInterestBearingBalance",
            "TreasuryInterestBearingAverageBalance",
            "TreasuryHybridBalance",
            "TreasuryHybridAverageBalance",
        ]
    },
    "stage_counts": stage_counts,
    "eligibility_counts": eligibility_counts,
    "first_loss_stage": first_loss_stage,
    "target_aggregate_rows": rows(target_aggregate_positive, ["RelationshipGuid", "DatePartition", "DepositType", "Balance"]),
    "target_relationship_rows": rows(relationship_target, ["RelationshipId", "RelationshipName", "DatePartition", "OwnerName", "RegionName"]),
    "target_aggregate_raw_rows": rows(aggregate_target, ["RelationshipNewId", "RelationshipId", "DatePartition", "ZeroInterestDepositBalance", "InterestBearingDepositBalance", "TimedDepositBalance", "TreasuryInterestBearingBalance", "TreasuryInterestBearingAverageBalance", "TreasuryHybridBalance", "TreasuryHybridAverageBalance"]),
    "target_account_rows": rows(target_account_raw, ["OpportunityId", "OpportunityName", "RelationshipId", "AccountType", "DepositProductType", "OpportunityStageStatus", "OpportunityIsDeleted", "ScenarioType", "CloseDate", "OpportunityDepositAverageBalance", "OpportunityOtherIncome"]),
    "target_d2p_rows": rows(target_d2p, ["DatePartition", "OpportunityId", "OpportunityName", "RelationshipGuid", "RelationshipName", "DepositType", "LastRaRunDate", "LastCoreBalancePerDepositType", "LastCoreBalanceAllDeposits"]),
}
dbutils.notebook.exit(json.dumps(result, default=str, sort_keys=True))
