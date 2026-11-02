# Databricks notebook source
"""Load reviewed, source-pinned functions without application imports or I/O."""

from __future__ import annotations

import ast
import datetime as datetime_module
import hashlib
import io
import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pandas as pd
from pyspark.sql import Window, functions as F, types as T
from pyspark.sql.utils import AnalysisException

spark = spark.newSession()
spark.conf.set("spark.sql.session.timeZone", "UTC")
spark.conf.set("spark.sql.shuffle.partitions", "2")
spark.conf.set("spark.sql.ansi.enabled", "false")
FIXTURE = PAYLOAD["fixtures"]
SOURCES = PAYLOAD["sources"]
for _source in SOURCES.values():
    assert hashlib.sha256(_source["text"].encode()).hexdigest() == _source["sha256"]
LOGGER = SimpleNamespace(
    info=lambda *a: None, warning=lambda *a: None, debug=lambda *a: None
)


class FixtureExit(Exception):
    """Represent an intercepted application exit without terminating the suite."""


def _exit(*args: Any, **kwargs: Any) -> None:
    raise FixtureExit("application exit intercepted")


def _load(
    source_id: str,
    functions: list[str],
    classes: dict | None = None,
    extra: dict | None = None,
) -> dict:
    """Compile only explicitly selected definitions and literal constants."""
    env = dict(
        F=F,
        StringType=T.StringType,
        Window=Window,
        pd=pd,
        pandas=pd,
        dt=datetime,
        datetime=datetime_module,
        timedelta=timedelta,
        timezone=timezone,
        AnalysisException=AnalysisException,
        DI_DATESTAMP_FORMAT="%Y%m%d",
        DI_TIMESTAMP_FORMAT="%Y%m%d-%H%M%S",
        log_empty_dataset_and_exit=_exit,
        log_info_and_exit=_exit,
        log_error_and_exit=_exit,
        DataValidationError=ValueError,
        DatePartitionVersionPartition=lambda **kw: SimpleNamespace(**kw),
        DerivedRaRunIdToReplace=lambda **kw: SimpleNamespace(**kw),
    )
    env.update(extra or {})
    tree = ast.parse(SOURCES[source_id]["text"])
    body = [
        ast.ImportFrom(
            module="__future__", names=[ast.alias(name="annotations")], level=0
        )
    ]
    found = set()
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            try:
                ast.literal_eval(node.value)
            except (ValueError, TypeError):
                continue
            body.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in functions:
            body.append(node)
            found.add(node.name)
        elif isinstance(node, ast.ClassDef) and node.name in (classes or {}):
            selected = [
                n
                for n in node.body
                if isinstance(n, ast.FunctionDef) and n.name in classes[node.name]
            ]
            assert {n.name for n in selected} == set(classes[node.name]), node.name
            node.body, node.bases, node.keywords, node.decorator_list = (
                selected,
                [],
                [],
                [],
            )
            body.append(node)
    assert found == set(functions), (source_id, set(functions) - found)
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])),
            source_id,
            "exec",
        ),
        env,
    )
    return env


HELPERS = _load(
    "helpers",
    [
        "has_column",
        "generate_column_aliases",
        "select_and_rename_columns",
        "get_latest_entry_by_date",
        "get_largest_entry_by_value",
        "replace_special_chars",
        "pandas_select_and_rename_columns",
        "change_column_data_type",
    ],
)
DH = SimpleNamespace(**{k: v for k, v in HELPERS.items() if not k.startswith("__")})
DERIVED = _load(
    "derived_job",
    [
        "filter_account_level",
        "get_deposit_account_data",
        "make_core_deposit_time_series",
        "add_summary_columns_to_core_deposits",
        "normalize_treasury_deposit_types",
        "add_deposits_promised_by_type",
        "add_delivery_window_start_stats",
        "calculate_delivery_window_stats",
        "convert_to_long_format",
    ],
    {"DeliveryToPromise": ["_run"]},
    {"dh": DH},
)
SPARK_LOADER = _load(
    "spark_download_helpers",
    [
        "has_columns",
        "get_latest_entry_by_value",
        "filter_latest_minor_version_per_id_cols",
        "filter_less_than_equal_to_date_col",
    ],
)
PANDAS_LOADER = _load(
    "pandas_download_helpers",
    [
        "has_columns",
        "rank",
        "row_number",
        "get_latest_entry_by_value",
        "filter_latest_minor_version_per_id_cols",
        "filter_less_than_equal_to_date_col",
    ],
)
SNAPSHOT = _load(
    "snapshot_runner",
    [],
    {"ParquetSnapshotRunner": ["add_keyhash_col", "resolve_change_data"]},
)
SNAPSHOT.update(
    _load(
        "snapshot_runner",
        [],
        {"OpportunitiesSnapshotRunner": ["get_latest_entry_by_date"]},
        {"ParquetSnapshotRunner": SNAPSHOT["ParquetSnapshotRunner"]},
    )
)
RA = _load(
    "ra_runner",
    [],
    {
        "DerivedRaRunner": [
            "deterministically_remove_duplicates",
            "validate_distinctness",
            "_identify_new_run_partitions_to_add_update",
            "set_partitions",
        ]
    },
)
HISTORY = _load(
    "history_job",
    [
        "define_column_selection",
        "get_scenario_level_fields",
        "get_account_level_fields",
        "get_scenarios_with_no_accounts",
    ],
    extra={"dh": DH},
)
TREASURY = _load(
    "treasury_assumptions_job", [], {"CoreTreasuryProductAssumptionsData": ["_run"]}
)
REPORT = _load(
    "report_job",
    [],
    {"DeliveryToPromise": ["_run", "run"]},
    {
        "dh": DH,
        "fmt": SimpleNamespace(
            CLIENT_TIMESTAMP_FORMAT_PYTHON="%Y-%m-%d %I:%M:%S %p",
            CLIENT_DATESTAMP_FORMAT_PYTHON="%Y-%m-%d",
        ),
    },
)
WRITER = _load(
    "spark_uploader",
    [],
    {"SparkDatasetUploader": ["_select_and_cast_dtypes"]},
    {"dh": DH},
)


def _frame(rows: list[dict], schema: str) -> Any:
    """Create a bounded, explicitly typed synthetic Spark frame."""
    assert len(rows) <= 32
    return spark.createDataFrame(rows, schema=schema)


def _markers(frame: Any) -> list[str]:
    return sorted(r["Marker"] for r in frame.select("Marker").collect())


class MemoryDownloader:
    """Inject preselected frames while preventing every download and upload."""

    def __init__(self, frames: dict, missing: bool = False) -> None:
        self.frames, self.missing = frames, missing

    def set_uris(self) -> None:
        return None

    def set_contx_paths(self) -> None:
        return None

    def download(self) -> None:
        return None

    def is_missing_required_dataset(self) -> bool:
        return self.missing

    def filter_less_than_equal_to_date_col(self) -> None:
        return None

    def filter_latest_minor_version_per_id_cols(self) -> None:
        return None

    def return_df(self, name: str) -> Any:
        return self.frames[name]


def _factory(frames: dict, missing: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        from_runner=lambda *a, **kw: MemoryDownloader(frames, missing)
    )
