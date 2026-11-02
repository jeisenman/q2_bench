# Databricks notebook source
"""Bind unchanged application modules to fixture-backed I/O and runner context."""

from __future__ import annotations

import ast
import copy
import datetime as datetime_module
import io
import os
from collections.abc import MutableMapping
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pandas as pd
from pyspark.sql import Window, functions as F, types as T

spark = spark.newSession()
spark.conf.set("spark.sql.session.timeZone", "UTC")
spark.conf.set("spark.sql.shuffle.partitions", "2")
spark.conf.set("spark.sql.ansi.enabled", "false")
FIXTURE, SOURCES = PAYLOAD["fixtures"], PAYLOAD["sources"]
LOGGER = SimpleNamespace(
    info=lambda *a: None, warning=lambda *a: None, debug=lambda *a: None
)
PATCHES = ExitStack()
PATCH_LEDGER = []


class FixtureExit(Exception):
    """Capture an application's explicit exit without stopping other cases."""


def _exit(*args: Any, **kwargs: Any) -> None:
    raise FixtureExit("application exit intercepted")


def _patch(module: Any, name: str, value: Any) -> None:
    PATCHES.enter_context(patch.object(module, name, value, create=True))
    PATCH_LEDGER.append(module.__name__ + "." + name)


for _module in MODULES.values():
    for _name in [
        "log_empty_dataset_and_exit",
        "log_info_and_exit",
        "log_error_and_exit",
    ]:
        if hasattr(_module, _name):
            _patch(_module, _name, _exit)

REAL_RA = MODULES["ra_runner"].DerivedRaRunner


class FixtureRa(REAL_RA):
    """Supply abstract metadata/context boundaries; inherit every tested method."""

    @property
    def primary_source_meta_data(self) -> Any:
        """Return fixture metadata at the runner's primary input boundary."""
        return self._fixture_primary

    @property
    def derived_sink_meta_data(self) -> Any:
        """Return fixture metadata at the runner's derived sink boundary."""
        return self._fixture_sink

    def _run(self) -> Any:
        raise AssertionError("abstract RA transform is outside this fixture")


class RunnerFacade:
    """Configure real runner properties without connecting framework setup."""

    def __init__(self, cls: type) -> None:
        """Create the original runner with an isolated framework context."""
        concrete = FixtureRa if cls is REAL_RA else cls
        real = object.__new__(concrete)
        object.__setattr__(self, "real", real)
        real._logger, real._spark_session, real._activity = LOGGER, spark, None
        real._context, real._jobname = None, "synthetic-module-validation"
        real._fixture_primary = None
        real._fixture_sink = SimpleNamespace(
            LATEST_MAJOR_VERSION=1, LATEST_MINOR_VERSION=0
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self.real, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in {"logger", "activity", "context", "jobname"}:
            setattr(self.real, "_" + name, value)
        elif name == "source_meta_data" and isinstance(
            getattr(type(self.real), name, None), property
        ):
            assert value == [], "fixture may not override real source metadata"
        elif name == "primary_source_meta_data" and isinstance(self.real, FixtureRa):
            self.real._fixture_primary = value
        elif name == "current_version" and isinstance(self.real, FixtureRa):
            major, minor = value.removeprefix("v").split(".")
            self.real._fixture_sink = SimpleNamespace(
                LATEST_MAJOR_VERSION=int(major), LATEST_MINOR_VERSION=int(minor)
            )
        else:
            setattr(self.real, name, value)


class ClassFacade:
    """Retain original class methods while isolating runner initialization."""

    def __init__(self, cls: type) -> None:
        """Retain the imported class for original method dispatch."""
        self.cls = cls

    def __call__(self) -> RunnerFacade:
        return RunnerFacade(self.cls)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.cls, name)


class Namespace(MutableMapping):
    """Route dataset monkey patches into the real imported module globals."""

    def __init__(self, module: Any) -> None:
        """Bind the shared-cell interface to a real imported module."""
        self.module = module

    def __getitem__(self, key: str) -> Any:
        value = getattr(self.module, key)
        if key in {
            "DeliveryToPromise",
            "CoreTreasuryProductAssumptionsData",
            "DerivedRaRunner",
            "DispatchL3LibraryDatafeedsV2",
        }:
            return ClassFacade(value)
        return value

    def __setitem__(self, key: str, value: Any) -> None:
        if key == "SOURCE_MD" and value == []:
            return  # Keep actual dataset metadata; replace only its transport.
        _patch(self.module, key, value)

    def __delitem__(self, key: str) -> None:
        raise TypeError("module definitions cannot be deleted")

    def __iter__(self) -> Any:
        return iter(vars(self.module))

    def __len__(self) -> int:
        return len(vars(self.module))


def _load(
    source_id: str,
    functions: list,
    classes: dict | None = None,
    extra: dict | None = None,
) -> Namespace:
    """Compatibility entrypoint: return a full module, never extract AST bodies."""
    module = MODULES[source_id]
    for key, value in (extra or {}).items():
        if key != "MoreThanOneDatafeedRecord":
            _patch(module, key, value)
    return Namespace(module)


HELPERS = Namespace(MODULES["helpers"])
DH = MODULES["helpers"]
DERIVED = Namespace(MODULES["derived_job"])
SPARK_LOADER = Namespace(MODULES["spark_download_helpers"])
PANDAS_LOADER = Namespace(MODULES["pandas_download_helpers"])
SNAPSHOT = Namespace(MODULES["snapshot_runner"])
RA = Namespace(MODULES["ra_runner"])
HISTORY = Namespace(MODULES["history_job"])
TREASURY = Namespace(MODULES["treasury_assumptions_job"])
REPORT = Namespace(MODULES["report_job"])
WRITER = Namespace(MODULES["spark_uploader"])


def _frame(rows: list[dict], schema: str) -> Any:
    assert len(rows) <= 32
    return spark.createDataFrame(rows, schema=schema)


def _markers(frame: Any) -> list[str]:
    return sorted(row.Marker for row in frame.select("Marker").collect())


class MemoryDownloader:
    """Keep real metadata and selectors while replacing dataset acquisition."""

    def __init__(self, frames: dict, metadata: Any, missing: bool) -> None:
        """Copy source metadata and bind bounded synthetic datasets."""
        self.frames = dict(frames)
        self.metadata = {}
        self.missing = missing
        for original in metadata if isinstance(metadata, list) else [metadata]:
            md = copy.copy(original)
            name = md.data_source_name
            frame = self.frames.get(name)
            # PandasDatasetDownloader.download normalizes an empty read to None.
            if isinstance(frame, pd.DataFrame) and frame.empty:
                frame = None
                self.frames[name] = None
            if frame is not None:
                columns = set(frame.columns)
                additions = {
                    md.date_col: 20261029
                    if md.date_col == "DatePartition"
                    else "20261029-050000",
                    "VersionPartition": f"v{md.major_version}.{md.minor_version if md.minor_version is not None else type(md).LATEST_MINOR_VERSION}",
                }
                additions.update(
                    {
                        key: "SYN_META_" + key
                        for key in md.id_cols
                        if key not in additions and "." not in key
                    }
                )
                for key, value in additions.items():
                    if key not in columns:
                        if isinstance(frame, pd.DataFrame):
                            frame[key] = value
                        else:
                            frame = frame.withColumn(key, F.lit(value))
                self.frames[name] = frame
            md.df = frame
            self.metadata[name] = md

    def set_uris(self) -> None:
        """Intercept physical Spark path discovery."""
        return None

    def set_contx_paths(self) -> None:
        """Intercept physical Pandas path discovery."""
        return None

    def download(self) -> None:
        """Use injected datasets without contacting storage."""
        return None

    def is_missing_required_dataset(self) -> bool:
        """Apply the source metadata's required-input boundary."""
        return self.missing or any(
            md.required and md.df is None for md in self.metadata.values()
        )

    def filter_less_than_equal_to_date_col(self) -> None:
        """Apply original selectors at the pinned fixture clock."""
        for name, md in self.metadata.items():
            if md.df is not None:
                module = (
                    PANDAS_LOADER if isinstance(md.df, pd.DataFrame) else SPARK_LOADER
                )
                md.df = module["filter_less_than_equal_to_date_col"](
                    md, datetime(2026, 10, 29, 5, tzinfo=timezone.utc)
                )
                self.frames[name] = md.df

    def filter_latest_minor_version_per_id_cols(self) -> None:
        """Apply original version selectors to every supplied dataset."""
        for name, md in self.metadata.items():
            if md.df is not None:
                module = (
                    PANDAS_LOADER if isinstance(md.df, pd.DataFrame) else SPARK_LOADER
                )
                md.df = module["filter_latest_minor_version_per_id_cols"](md)
                self.frames[name] = md.df

    def return_df(self, name: str) -> Any:
        """Return the selected synthetic dataset or an absent optional input."""
        return self.frames.get(name)


def _factory(frames: dict, missing: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        from_runner=lambda metadata, **kw: MemoryDownloader(frames, metadata, missing)
    )


_actual_notebook_exit = dbutils.notebook.exit


def _finish_modules(text: str) -> None:
    value = json.loads(text)
    value["execution_mode"] = "imported_modules_monkey_patched_datasets"
    value["imported_modules"] = MODULE_PROVENANCE
    value["import_dependency_versions"] = IMPORT_VERSIONS
    value["application_pins"] = {
        "di-pipelines": "fd9d9b74b53946150a01ed68fb87e4ffa4b7bc1e",
        "di-pyjobs": "32fbfc493d7f039def61c157e579caf24288db48",
        "di-model-server": "7b73b3cdc2b44d29758e5733cf05e7e246dd717d",
    }
    loaded = {}
    namespaces = []
    for name, module in list(sys.modules.items()):
        if name.split(".")[0] not in {"datascience_jobs", "di_pyjobs", "dimodels"}:
            continue
        if not getattr(module, "__file__", None):
            paths = list(getattr(module, "__path__", []))
            if not paths or any(
                not pathlib.Path(p).resolve().is_relative_to(MODULE_ROOT) for p in paths
            ):
                raise ValueError("Application namespace escaped pinned source: " + name)
            namespaces.append(name)
            continue
        source = pathlib.Path(module.__file__).resolve()
        if not source.is_relative_to(MODULE_ROOT):
            raise ValueError("Application import escaped pinned source: " + name)
        loaded[name] = hashlib.sha256(source.read_bytes()).hexdigest()
    value["loaded_application_source_sha256"] = loaded
    value["pinned_namespace_packages"] = sorted(namespaces)
    value["patch_count"] = len(PATCH_LEDGER)
    value["history_execution_mode"] = PAYLOAD.get("history_mode", "full")
    value["scope"] = (
        "Original modules and inheritance retained; dataset transport, runner setup, storage, clock and uploads patched. "
        "Optional-product cases capture original account construction and original union on three identity columns; "
        "remaining History formatting and full output schema are outside that boundary."
    )
    PATCHES.close()
    _actual_notebook_exit(json.dumps(value, sort_keys=True, default=str))


PATCHES.enter_context(patch.object(dbutils.notebook, "exit", _finish_modules))
