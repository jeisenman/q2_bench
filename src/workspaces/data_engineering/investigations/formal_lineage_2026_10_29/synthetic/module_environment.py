# Databricks notebook source
"""Load complete pinned application packages in a per-run temporary directory."""

from __future__ import annotations

import base64
import importlib
import importlib.metadata
import inspect
import io
import json
import hashlib
import pathlib
import subprocess
import sys
import tempfile
import zipfile

MODULE_ROOT = pathlib.Path(tempfile.mkdtemp(prefix="d2p-module-validation-"))
DEPENDENCY_ROOT = MODULE_ROOT / "dependencies"
# Import-time infrastructure dependencies from the pinned di-pyjobs manifest.
# No Spark, Pandas, NumPy or PyArrow installation or cluster-library changes.
IMPORT_REQUIREMENTS = [
    "SQLAlchemy==1.4.54",
    "azure-storage-file-datalake==12.21.0",
    "azure-storage-blob==12.26.0",
    "azure-identity==1.25.1",
    "snowflake-connector-python==3.18.0",
    "fastavro==1.12.0",
    "pyopenssl==25.3.0",
    "cryptography==46.0.0",
    "asn1crypto==1.5.1",
    "sortedcontainers==2.4.0",
    "tomlkit==0.14.0",
    "greenlet==3.3.1",
    "msal==1.34.0",
    "msal-extensions==1.3.1",
    "pyjwt==2.11.0",
    "azure-core==1.38.0",
    "isodate==0.7.2",
    "typing-extensions==4.15.0",
]
_installed = subprocess.run(
    [
        sys.executable,
        "-m",
        "pip",
        "--isolated",
        "install",
        "--disable-pip-version-check",
        "--index-url",
        "https://pypi.org/simple",
        "--no-deps",
        "--target",
        str(DEPENDENCY_ROOT),
        *IMPORT_REQUIREMENTS,
    ],
    capture_output=True,
    text=True,
    timeout=600,
    check=False,
)
if _installed.returncode:
    raise RuntimeError(
        "Isolated import dependencies failed to install; return code "
        + str(_installed.returncode)
    )

with zipfile.ZipFile(
    io.BytesIO(base64.b64decode(PAYLOAD["application_archive"]))
) as _archive:
    for _item in _archive.infolist():
        _path = pathlib.PurePosixPath(_item.filename)
        if (
            _path.is_absolute()
            or ".." in _path.parts
            or not _item.filename.endswith(".py")
        ):
            raise ValueError("Unexpected application archive member")
    _archive.extractall(MODULE_ROOT)
sys.path[:0] = [
    str(MODULE_ROOT / "di-pipelines/ds-jobs/src"),
    str(MODULE_ROOT / "di-pyjobs"),
    str(MODULE_ROOT / "di-model-server/di-models"),
    str(DEPENDENCY_ROOT),
]
MODULE_NAMES = {
    "helpers": "datascience_jobs.utils.datascience_helpers",
    "derived_job": "datascience_jobs.jobs.data.delivery_to_promise.delivery_to_promise_data",
    "spark_download_helpers": "datascience_jobs.dataset_downloader.downloaders.spark_dataset_downloader_helpers",
    "pandas_download_helpers": "datascience_jobs.dataset_downloader.downloaders.pandas_dataset_downloader_helpers",
    "snapshot_runner": "datascience_jobs.runner.derived",
    "ra_runner": "datascience_jobs.jobs.data.ra.utils.ra_job_template",
    "history_job": "datascience_jobs.jobs.data.account_level_opportunities.account_level_opportunities_history_event_bus",
    "treasury_assumptions_job": "datascience_jobs.jobs.data.products.core_treasury_product_assumptions_data",
    "report_job": "datascience_jobs.jobs.reports.delivery_to_promise.delivery_to_promise_report",
    "spark_uploader": "datascience_jobs.dataset_uploader.uploaders.spark_dataset_uploader",
    "dispatch_job": "datascience_jobs.jobs.dispatch.library_datafeeds_v2",
}
MODULES = {}
MODULE_PROVENANCE = {}
IMPORT_VERSIONS = {}
for _requirement in IMPORT_REQUIREMENTS:
    _package, _version = _requirement.split("==")
    _actual_version = importlib.metadata.version(_package)
    if _actual_version != _version:
        raise ValueError("Import dependency version differs from pin: " + _package)
    IMPORT_VERSIONS[_package] = _actual_version
for _id, _name in MODULE_NAMES.items():
    _module = importlib.import_module(_name)
    _bytes = pathlib.Path(_module.__file__).read_bytes()
    _hash = hashlib.sha256(_bytes).hexdigest()
    if _hash != PAYLOAD["sources"][_id]["sha256"]:
        raise ValueError("Imported application source differs from pin: " + _name)
    MODULES[_id] = _module
    MODULE_PROVENANCE[_id] = dict(module=_name, sha256=_hash, imported_full_module=True)
