# Databricks notebook source
"""Evaluate isolated source functions on independently specified fixtures."""

from __future__ import annotations


def _evaluate_stage(case: dict) -> dict:
    """Return only the observable fields declared by one fixture."""
    stage, data = case["stage"], case["data"]
    if stage == "opportunity":
        rows = [FIXTURE["control_row"], data["row"]]
        schema = (
            "Marker string, OpportunityOtherIncome double, OpportunityDepositAverageBalance double, "
            "OpportunityStageStatus string, OpportunityIsDeleted boolean, ScenarioType string, "
            "RelationshipId string, CloseDate string"
        )
        for row in rows:
            for key in ["OpportunityOtherIncome", "OpportunityDepositAverageBalance"]:
                row[key] = float(row[key]) if row[key] is not None else None
        output = DERIVED["filter_account_level"](
            _frame(rows, schema), FIXTURE["run_date"], 1096
        )
        return {"markers": _markers(output)}
    if stage == "versions":
        frame = (
            _frame(data["rows"], "Key string, Marker string, VersionPartition string")
            if data["backend"] == "spark"
            else pd.DataFrame(data["rows"])
        )
        md = SimpleNamespace(
            df=frame, major_version=1, minor_version=data["minor"], id_cols=["Key"]
        )
        namespace = SPARK_LOADER if data["backend"] == "spark" else PANDAS_LOADER
        out = namespace["filter_latest_minor_version_per_id_cols"](md)
        return {
            "markers": _markers(out)
            if data["backend"] == "spark"
            else sorted(out.Marker.tolist())
        }
    if stage == "asof":
        column = data["column"]
        rows = [
            {"Marker": marker, column: value}
            for marker, value in zip(
                ["before", "equal", "after", "null"], data["values"]
            )
        ]
        dtype = "int" if column == "DatePartition" else "string"
        frame = (
            _frame(rows, f"Marker string, {column} {dtype}")
            if data["backend"] == "spark"
            else pd.DataFrame(rows)
        )
        if data["backend"] == "pandas" and column == "DatePartition":
            frame[column] = pd.array(frame[column], dtype="Int64").astype("string")
        md = SimpleNamespace(df=frame, date_col=column)
        namespace = SPARK_LOADER if data["backend"] == "spark" else PANDAS_LOADER
        out = namespace["filter_less_than_equal_to_date_col"](
            md, datetime(2026, 10, 29, 5, tzinfo=timezone.utc)
        )
        return {
            "markers": _markers(out)
            if data["backend"] == "spark"
            else sorted(out.Marker.tolist())
        }
    if stage == "ranking":
        frame = _frame(data["rows"], "Key string, Marker string, Value int")
        out = DH.get_latest_entry_by_date(
            frame, ["Key"], "Value", getattr(F, data["rank"])
        )
        if case["expected"].get("ambiguous"):
            return {
                "count": out.count(),
                "ambiguous": len({r["Marker"] for r in data["rows"]}) > 1,
            }
        return {"markers": _markers(out)}
    if stage == "account_extract":
        row = dict(
            OpportunityId="SYN_OPP",
            PricingDate="2026-10-01",
            DepositAmount=100.0,
            CdOriginationDate="2026-01-01",
            DepositProductType="TimedDeposit",
            CdTerm=12,
            AccountType=data["account_type"],
        )
        frame = _frame(
            [row],
            "OpportunityId string, PricingDate string, DepositAmount double, CdOriginationDate string, DepositProductType string, CdTerm int, AccountType string",
        )
        return {
            "count": DERIVED["get_deposit_account_data"](
                frame, DERIVED["ACCOUNT_COLUMNS"]
            ).count()
        }
    if stage == "promised":
        opp = _frame([{"OpportunityId": "SYN_OPP"}], "OpportunityId string")
        row = dict(
            OpportunityId="SYN_OPP",
            DepositType=data["type"],
            DepositAmount=data["balance"],
            MaturityDate=data["maturity"],
            PricingDate=data["pricing"],
        )
        if row["DepositAmount"] is not None:
            row["DepositAmount"] = float(row["DepositAmount"])
        deposits = _frame(
            [row],
            "OpportunityId string, DepositType string, DepositAmount double, MaturityDate string, PricingDate string",
        )
        out = DERIVED["add_deposits_promised_by_type"](opp, deposits).collect()
        assert len(out) == 1
        return {
            "deposit_type": out[0].DepositType,
            "promised": out[0].OppDepositsPromised,
        }
    if stage == "core_positive":
        value = float(data["balance"]) if data["balance"] is not None else None
        frame = _frame(
            [
                dict(
                    RelationshipGuid="SYN_REL",
                    DatePartition="20261001",
                    ZeroInterestDepositBalance=value,
                    InterestBearingDepositBalance=0.0,
                    TimedDepositBalance=0.0,
                    TreasuryInterestBearingBalance=0.0,
                    TreasuryHybridBalance=0.0,
                )
            ],
            "RelationshipGuid string, DatePartition string, ZeroInterestDepositBalance double, InterestBearingDepositBalance double, TimedDepositBalance double, TreasuryInterestBearingBalance double, TreasuryHybridBalance double",
        )
        # This predicate is exercised in its original context by full_job fixtures too.
        return {
            "count": DERIVED["convert_to_long_format"](frame)
            .filter(F.col("Balance") > 0)
            .count()
        }
    if stage == "timeseries":
        date = (datetime(2026, 10, 29) - timedelta(days=data["offset"])).strftime(
            "%Y%m%d"
        )
        frame = _frame(
            [
                dict(
                    RelationshipGuid="SYN_REL",
                    DepositType="ZeroInterestDemand",
                    DatePartition=date,
                    Balance=100.0,
                )
            ],
            "RelationshipGuid string, DepositType string, DatePartition string, Balance double",
        )
        return {
            "count": DERIVED["make_core_deposit_time_series"](
                frame, FIXTURE["run_date"], 1096
            ).count()
        }
    if stage == "window":
        close = datetime(2023, 10, 30)
        core_date = (close + timedelta(days=data["days"])).strftime("%Y-%m-%d")
        row = dict(
            OpportunityId="SYN_OPP",
            DepositType="ZeroInterestDemand",
            OpportunityCloseDate=close.strftime("%Y-%m-%d"),
            OpportunityLastModified="2026-10-01",
            DatePartitionDate=core_date,
            CoreBalancePerDepositProductType=100.0,
            DaysInEffect=data.get("weight", 1),
        )
        frame = _frame(
            [row],
            "OpportunityId string, DepositType string, OpportunityCloseDate string, OpportunityLastModified string, DatePartitionDate string, CoreBalancePerDepositProductType double, DaysInEffect int",
        )
        d2p = frame.select("OpportunityId", "DepositType")
        start, forstats = DERIVED["add_delivery_window_start_stats"](d2p, frame, 36)
        result = DERIVED["calculate_delivery_window_stats"](
            start, forstats, data["months"]
        ).collect()[0]
        return {
            "average": result["AvgBalance" + str(data["months"])],
            "start": result.StartingBalance,
        }
    if stage == "writer":
        spark.conf.set("spark.sql.ansi.enabled", str(data["ansi"]).lower())
        try:
            frame = (
                _frame([dict(Other="x")], "Other string")
                if data.get("missing")
                else _frame([dict(Value=data["value"])], "Value string")
            )
            md = SimpleNamespace(
                df=frame, columns=["Value"], columns_spark_dtypes=[("Value", "int")]
            )
            try:
                out = (
                    WRITER["SparkDatasetUploader"]
                    ._select_and_cast_dtypes(md)
                    .df.collect()
                )
                return {"outcome": "rows", "value": out[0].Value}
            except Exception as error:
                return {"outcome": "error", "error_type": type(error).__name__}
        finally:
            spark.conf.set("spark.sql.ansi.enabled", "false")
    return _evaluate_upstream(case)
