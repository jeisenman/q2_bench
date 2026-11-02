# Databricks notebook source
"""Run synthetic cases and emit explicit pass/fail evidence."""

from __future__ import annotations

import math
import time


def _canonical(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (datetime_module.date, datetime_module.datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        return _canonical(value.item())
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _golden_report() -> dict:
    """Compare every final report column with the literal independent oracle."""
    assert GOLDEN is not None, "golden D2P transform did not complete"
    pdf = GOLDEN.toPandas()
    pdf["LastRaRunDate"] = pd.array(pdf.LastRaRunDate, dtype="Int64")
    REPORT["PandasDatasetDownloader"], REPORT["SOURCE_MD"] = (
        _factory({"DeliveryToPromiseData": pdf}),
        [],
    )
    runner = REPORT["DeliveryToPromise"]()
    runner.logger = LOGGER
    out = runner.run()
    actual = [
        {key: _canonical(value) for key, value in row.items()}
        for row in out.to_dict("records")
    ]
    assert list(out.columns) == list(PAYLOAD["golden"][0]), (
        "report column order mismatch"
    )
    assert actual == PAYLOAD["golden"], (
        "full 50-column reporting row differs from literal oracle"
    )
    return {"rows": actual, "column_count": len(out.columns)}


RESULTS = []
for _case in FIXTURE["cases"]:
    _started = time.monotonic()
    print("Synthetic scenario starting:", _case["id"], flush=True)
    try:
        if _case["stage"] == "full_job":
            _actual = _full_job(_case["data"])
        elif _case["stage"] == "report":
            _actual = _report(_case["data"])
        elif _case["stage"] == "dispatch":
            _actual = _dispatch(_case["data"])
        else:
            _actual = _evaluate_stage(_case)
        if _actual.get("outcome") == "error":
            assert _actual.get("error_type") not in {
                "NameError",
                "AttributeError",
                "KeyError",
                "AssertionError",
            }, _actual
        for _key, _expected in _case["expected"].items():
            assert _canonical(_actual.get(_key)) == _expected, (
                _key,
                _expected,
                _actual,
            )
        RESULTS.append(
            dict(id=_case["id"], stage=_case["stage"], status="pass", observed=_actual)
        )
    except Exception as _error:
        RESULTS.append(
            dict(
                id=_case["id"],
                stage=_case["stage"],
                status="fail",
                error_type=type(_error).__name__,
                error=str(_error)[:700],
            )
        )
    RESULTS[-1]["seconds"] = round(time.monotonic() - _started, 3)
    print(
        "Synthetic scenario completed:", _case["id"], RESULTS[-1]["status"], flush=True
    )
if any(
    c["stage"] == "full_job" and c["data"]["mode"] == "golden" for c in FIXTURE["cases"]
):
    try:
        RESULTS.append(
            dict(
                id="golden_report_all_50_columns",
                stage="integration",
                status="pass",
                observed=_golden_report(),
            )
        )
    except Exception as _error:
        RESULTS.append(
            dict(
                id="golden_report_all_50_columns",
                stage="integration",
                status="fail",
                error_type=type(_error).__name__,
                error=str(_error)[:700],
            )
        )
SUMMARY = dict(
    format="q2-d2p-synthetic-result/v1",
    synthetic=True,
    spark_version=spark.version,
    pandas_version=pd.__version__,
    timezone=spark.conf.get("spark.sql.session.timeZone"),
    ansi_default=FIXTURE["ansi_default"],
    status="pass" if all(r["status"] == "pass" for r in RESULTS) else "fail",
    cases=RESULTS,
    passed=sum(r["status"] == "pass" for r in RESULTS),
    failed=sum(r["status"] == "fail" for r in RESULTS),
    source_sha256={key: value["sha256"] for key, value in SOURCES.items()},
    scope="Pinned function/method execution on synthetic memory inputs; loaders, cloud storage and path construction intercepted; no Airflow or real writer execution.",
)
dbutils.notebook.exit(json.dumps(SUMMARY, sort_keys=True, default=str))
