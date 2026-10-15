"""Build the Databricks KPO sizing inventory from di-pipelines overrides."""

import argparse
import ast
import json
from pathlib import Path
from typing import Any

JOB_SOURCES = {
    "RELATIONSHIP_SIGNALS_TIME_SERIES_AGG_CP_TO_SNOWFLAKE_ARGS": [
        {
            "job": "relationship_signals_time_series_agg_cp_to_snowflake",
            "kind": "historical",
            "historical_scope": "version_root",
            "dataset": "PL_RelationshipAwareness/Relationships/RelationshipSignalsTimeSeriesAgg",
            "stage": "Derived",
            "version": "v1.0",
        },
    ],
    "CORE_LOAN_AMORTIZATION_OPERATOR_ARGS": [
        {
            "job": "get_core_loan_amortization_tables",
            "kind": "ra_file",
            "path": "DatabaseOutput/dbStagingCoreLoanAmortizationTables.csv",
        },
    ],
    "ASSUMPTION_SETS_OPERATOR_ARGS": [
        {
            "job": "get_assumption_sets",
            "kind": "ra_file",
            "path": "ApplicationInput/AssumptionSets.csv",
        },
    ],
    "ASSUMPTION_SETS_COPY_OPERATOR_ARGS": [
        {
            "job": "assumption_sets_to_internal_adls",
            "kind": "historical",
            "dataset": "PL_RelationshipAwareness/Assumptions/AssumptionSets",
            "stage": "Primary",
            "version": "v1.0",
        },
        {
            "job": "assumption_sets_to_client_datamart_adls",
            "kind": "historical",
            "dataset": "PL_RelationshipAwareness/Assumptions/AssumptionSets",
            "stage": "Primary",
            "version": "v1.0",
        },
    ],
    "OTHER_FINANCIAL_STATEMENT_BREAKDOWN_ARGS": [
        {
            "job": "get_other_financial_statement_breakdown",
            "kind": "ra_file",
            "path": "DatabaseOutput/dbStagingOtherAccountFinancialStatementBreakdowns.csv",
        },
    ],
    "LOAN_FINANCIAL_STATEMENT_BREAKDOWN_ARGS": [
        {
            "job": "get_loan_financial_statement_breakdown",
            "kind": "ra_file",
            "path": "DatabaseOutput/dbStagingLoanFinancialStatementBreakdowns.csv",
        },
    ],
    "CORE_DEPOSIT_ACCOUNTS_ARGS": [
        {
            "job": "get_core_deposit_accounts",
            "kind": "ra_file",
            "path": "DatabaseOutput/dbStagingCoreDepositAccounts.csv",
        },
        {
            "job": "get_data_eng_core_deposit_account_metadata",
            "kind": "ra_file",
            "path": "DataEngineering/DataEngCoreDepositAccountMetadata.csv",
        },
    ],
    "CORE_DEPOSIT_ACCOUNTS_COPY_ARGS": [
        {
            "job": "high_quality_core_deposit_accounts_copy_client",
            "kind": "historical",
            "dataset": "PL_RelationshipAwareness/Core/CoreDepositAccounts",
            "stage": "Derived",
            "version": "v3.6",
        },
    ],
    "MONTHLY_CORE_DEPOSIT_ACCOUNTS_COPY_CLIENT_ARGS": [
        {
            "job": "monthly_core_deposit_accounts_copy_client",
            "kind": "historical",
            "dataset": "PL_RelationshipAwareness/Core/CoreDepositAccountsMonthly",
            "stage": "Derived",
            "version": "v3.6",
        },
    ],
    "TREASURY_FINANCIAL_STATEMENT_BREAKDOWN_ARGS": [
        {
            "job": "get_treasury_financial_statement_breakdown",
            "kind": "ra_file",
            "path": "DatabaseOutput/dbStagingTreasuryFinancialStatementBreakdowns.csv",
        },
    ],
    "CORE_OTHER_ACCOUNTS_OPERATOR_ARGS": [
        {
            "job": "get_core_other_accounts",
            "kind": "ra_file",
            "path": "DatabaseOutput/dbStagingCoreOtherAccounts.csv",
        },
        {
            "job": "get_data_eng_core_other_account_metadata",
            "kind": "ra_file",
            "path": "DataEngineering/DataEngCoreOtherAccountMetadata.csv",
        },
    ],
    "COMMERCIAL_LOAN_PRODUCTS_ARGS": [
        {
            "job": "get_commercial_loan_products",
            "kind": "ra_file",
            "path": "ApplicationInput/CommercialLoanProducts.csv",
        },
    ],
}


def _memory_gib(value: str) -> int:
    normalized = value.strip().lower()
    if not normalized.endswith("gi"):
        raise ValueError(f"Unsupported Kubernetes memory value: {value}")
    return int(normalized[:-2])


def _cpu_millicores(value: str) -> int:
    normalized = value.strip().lower()
    if normalized.endswith("m"):
        return int(normalized[:-1])
    return int(float(normalized) * 1000)


def _evaluate(node: ast.AST, values: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return values.get(node.id)
    if isinstance(node, ast.Dict):
        result: dict[Any, Any] = {}
        for key, value in zip(node.keys, node.values, strict=True):
            if key is None:
                result.update(_evaluate(value, values) or {})
            else:
                result[_evaluate(key, values)] = _evaluate(value, values)
        return result
    if isinstance(node, ast.Call):
        function_name = getattr(node.func, "id", "")
        if function_name == "V1ResourceRequirements":
            keywords = {
                item.arg: _evaluate(item.value, values) for item in node.keywords
            }
            requests = keywords.get("requests", {})
            limits = keywords.get("limits", {})
            memory = requests.get("memory") or limits.get("memory")
            cpu = requests.get("cpu") or limits.get("cpu")
            return {
                "cpu_millicores": _cpu_millicores(cpu),
                "memory_gib": _memory_gib(memory),
            }
        return None
    return None


def load_inventory(repo_root: Path) -> list[dict[str, Any]]:
    """Return explicit per-client KPO overrides and their measurable inputs."""
    allocation_path = repo_root / "dag-utils" / "resource_allocation.py"
    source = allocation_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(allocation_path))
    values: dict[str, Any] = {}
    override_groups: dict[str, dict[str, Any]] = {}

    for statement in tree.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if (
            isinstance(statement.value, ast.Call)
            and getattr(statement.value.func, "id", "") == "ClientArgOverrides"
        ):
            override_groups[target.id] = {
                keyword.arg: _evaluate(keyword.value, values)
                for keyword in statement.value.keywords
                if keyword.arg is not None
            }
        else:
            value = _evaluate(statement.value, values)
            if value is not None:
                values[target.id] = value

    inventory: list[dict[str, Any]] = []
    for group_name, jobs in JOB_SOURCES.items():
        group = override_groups[group_name]
        default_resource = (group.get("default") or {}).get("container_resources")
        for client_id, override in (group.get("client_overrides") or {}).items():
            resource = (override or {}).get("container_resources")
            if not resource:
                continue
            inventory.extend(
                {
                    **job,
                    "client_id": client_id,
                    "cpu_millicores": resource["cpu_millicores"],
                    "memory_gib": resource["memory_gib"],
                    "default_memory_gib": (default_resource or {}).get("memory_gib"),
                    "override_group": group_name,
                }
                for job in jobs
            )
    return inventory


def render_notebook(inventory: list[dict[str, Any]], source_commit: str) -> str:
    """Render a read-only Databricks SOURCE notebook."""
    inventory_json = json.dumps(inventory, separators=(",", ":"), sort_keys=True)
    return f"""# Databricks notebook source
# MAGIC %md
# MAGIC # KPO ADLS Size Inventory
# MAGIC
# MAGIC Read-only inventory of explicit per-client KubernetesPodOperator memory overrides.
# MAGIC It measures RA run files, dated Historical Data Mart partitions, or a full
# MAGIC VersionPartition root, then compares jobs by pod memory tier. Source commit: `{source_commit}`.
# COMMAND ----------
import json
from collections import deque
from pyspark.sql import functions as F
INVENTORY = json.loads({inventory_json!r})
SOURCE_COMMIT = {source_commit!r}
dbutils.widgets.text("client_ids", "", "Client UUIDs (comma-separated; blank = all)")
dbutils.widgets.text("default_storage_account", "pladls2usdatamartprod", "Default ADLS account")
dbutils.widgets.text("storage_account_overrides_json", '{{}}', "Client UUID to ADLS account JSON")
dbutils.widgets.dropdown("latest_only", "true", ["true", "false"], "Historical: latest DatePartition only")
dbutils.widgets.text("max_ra_requests", "30", "Maximum recent RA requests to inspect")
selected_clients = {{value.strip() for value in dbutils.widgets.get("client_ids").split(",") if value.strip()}}
account_overrides = json.loads(dbutils.widgets.get("storage_account_overrides_json"))
default_account = dbutils.widgets.get("default_storage_account").strip()
latest_only = dbutils.widgets.get("latest_only") == "true"
max_ra_requests = int(dbutils.widgets.get("max_ra_requests"))
if max_ra_requests < 1:
    raise ValueError("max_ra_requests must be at least 1")

def list_items(path):
    try:
        return list(dbutils.fs.ls(path))
    except Exception as error:
        raise RuntimeError(f"Unable to list ADLS path {{path}}: {{error}}") from error

def recursive_size(path):
    pending = deque([path])
    total_bytes = 0
    file_count = 0
    while pending:
        current = pending.popleft()
        for item in list_items(current):
            if item.isDir():
                pending.append(item.path)
            else:
                total_bytes += int(item.size)
                file_count += 1
    return total_bytes, file_count

def recent_ra_runs(root):
    requests = sorted(
        (item.path for item in list_items(root) if item.isDir() and "Request=" in item.path),
        reverse=True,
    )
    for request_path in requests[:max_ra_requests]:
        runs = sorted(
            (item.path for item in list_items(request_path) if item.isDir() and "RaRun=" in item.path),
            reverse=True,
        )
        yield from runs

def measure_ra_file(row, account):
    root = f"abfss://datalake@{{account}}.dfs.core.windows.net/ClientData/Client={{row['client_id']}}/DataIngress"
    for run_path in recent_ra_runs(root):
        target = run_path.rstrip("/") + "/" + row["path"]
        try:
            items = list_items(target)
        except Exception:
            continue
        if len(items) == 1 and not items[0].isDir():
            return int(items[0].size), 1, target
        total_bytes, file_count = recursive_size(target)
        return total_bytes, file_count, target
    raise FileNotFoundError(
        f"No matching {{row['path']}} found in the latest {{max_ra_requests}} requests under {{root}}"
    )

def measure_historical(row, account):
    dataset = row["dataset"].strip("/")
    root = (
        f"abfss://datalake@{{account}}.dfs.core.windows.net/"
        f"ClientId={{row['client_id']}}/L3/v1.0/{{row['stage']}}/{{dataset}}/"
        f"InstancePartition={{row['client_id']}}/VersionPartition={{row['version']}}"
    )
    historical_scope = row.get("historical_scope")
    if (
        historical_scope is None
        and row["job"] == "relationship_signals_time_series_agg_cp_to_snowflake"
    ):
        historical_scope = "version_root"
    if historical_scope == "version_root":
        total_bytes, file_count = recursive_size(root)
        return total_bytes, file_count, root
    if historical_scope not in (None, "date_partition"):
        raise ValueError(
            f"Unsupported historical_scope {{historical_scope!r}} for job {{row['job']}}"
        )
    partitions = sorted(
        (item.path for item in list_items(root) if item.isDir() and "DatePartition=" in item.path),
        reverse=True,
    )
    if not partitions:
        raise FileNotFoundError(f"No DatePartition directory found under {{root}}")
    targets = partitions[:1] if latest_only else partitions
    totals = [recursive_size(target) for target in targets]
    return sum(item[0] for item in totals), sum(item[1] for item in totals), ",".join(targets)

results = []
for row in INVENTORY:
    if selected_clients and row["client_id"] not in selected_clients:
        continue
    account = account_overrides.get(row["client_id"], default_account)
    result = {{**row, "storage_account": account, "source_commit": SOURCE_COMMIT}}
    try:
        if row["kind"] == "ra_file":
            total_bytes, file_count, measured_path = measure_ra_file(row, account)
        else:
            total_bytes, file_count, measured_path = measure_historical(row, account)
        result.update(
            status="measured",
            file_gib=round(total_bytes / (1024 ** 3), 3),
            file_count=file_count,
            measured_path=measured_path,
            error=None,
        )
    except Exception as error:
        result.update(
            status="unavailable",
            file_gib=None,
            file_count=None,
            measured_path=None,
            error=f"{{type(error).__name__}}: {{error}}",
        )
    results.append(result)

if not results:
    dbutils.notebook.exit("No inventory rows matched client_ids")
result_frame = spark.createDataFrame(results)
ordered = result_frame.orderBy(
    F.desc("memory_gib"),
    F.desc("cpu_millicores"),
    F.col("file_gib").desc_nulls_last(),
    F.asc("job"),
    F.asc("client_id"),
)
display(ordered)
# COMMAND ----------
# Same-runner peers make it easy to compare observed input sizes within each KPO memory tier.
peer_summary = (
    ordered.filter(F.col("status") == "measured")
    .groupBy("cpu_millicores", "memory_gib", "job")
    .agg(
        F.count("*").alias("measured_clients"),
        F.round(F.min("file_gib"), 3).alias("min_file_gib"),
        F.round(F.expr("percentile_approx(file_gib, 0.5)"), 3).alias("median_file_gib"),
        F.round(F.max("file_gib"), 3).alias("max_file_gib"),
    )
    .orderBy(F.desc("memory_gib"), F.desc("max_file_gib"), F.asc("job"))
)
display(peer_summary)
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--di-pipelines-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    inventory = load_inventory(args.di_pipelines_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        render_notebook(inventory, args.source_commit), encoding="utf-8"
    )
    print(f"Wrote {len(inventory)} KPO job/client rows to {args.output}")


if __name__ == "__main__":
    main()
