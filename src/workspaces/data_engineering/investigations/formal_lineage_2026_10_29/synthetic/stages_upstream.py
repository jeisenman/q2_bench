# Databricks notebook source
"""Evaluate upstream snapshot, ranking, branch and deduplication fixtures."""

from __future__ import annotations


def _evaluate_upstream(case: dict) -> dict:
    """Probe named upstream source functions on bounded synthetic inputs."""
    stage, data = case["stage"], case["data"]
    if stage in {"hq_delta", "hq_cap", "hq_rerun", "ra_dedup", "ra_distinct"}:
        runner = RA["DerivedRaRunner"]()
        runner.logger, runner.LAST_V2_RA_RUN = LOGGER, 20221115
        if stage == "ra_distinct":
            frame = _frame(data["rows"], "Key string, DatePartition int, Score int")
            try:
                out = runner.validate_distinctness(
                    frame,
                    SimpleNamespace(id_cols=["Key"], data_source_name="Synthetic"),
                )
                return {"outcome": "rows", "count": out.count()}
            except (ValueError, RA.get("DataValidationError", ValueError)) as error:
                return {"outcome": "error", "error_type": type(error).__name__}
        if stage == "hq_rerun":
            runner.activity = SimpleNamespace(parameters={}, window_start="2026-10-29")
            runner.current_version = "v1.0"
            runner.primary_source_df = _frame(
                [dict(DatePartition=d, RaRunId="r") for d in [20261001, 20261002]],
                "DatePartition int, RaRunId string",
            )
            runner.derived_sink_df = _frame(
                [
                    dict(
                        DatePartition=20261001,
                        VersionPartition="v1.0",
                        ProcessedWindowStart="2026-10-29",
                    )
                ],
                "DatePartition int, VersionPartition string, ProcessedWindowStart string",
            )
            runner.set_partitions()
            return {
                "dates": sorted(
                    r.DatePartition for r in runner.active_source_df.collect()
                )
            }
        if stage == "hq_delta":

            def rows(ids: list) -> list:
                return [
                    dict(DatePartition=20261001, RaRunId=v, VersionPartition="v1.0")
                    for v in ids
                ]

            schema = "DatePartition int, RaRunId string, VersionPartition string"
            a, b = runner._identify_new_run_partitions_to_add_update(
                _frame(rows(data["primary"]), schema),
                _frame(rows(data["sink"]), schema),
            )
            return {"active": a.count(), "replaced": b.count()}
        if stage == "hq_cap":
            runner.activity = SimpleNamespace(
                parameters={"date_partitions_upper_bound": data["cap"]},
                window_start="2026-10-29",
            )
            runner.primary_source_df = _frame(
                [dict(DatePartition=d, RaRunId="r") for d in [20261001, 20261002]],
                "DatePartition int, RaRunId string",
            )
            runner.derived_sink_df, runner.primary_source_meta_data = None, None
            runner.current_version = "v1.0"
            runner.generate_date_partitions = lambda md: {20261001, 20261002}
            runner.set_partitions()
            return {"count": runner.active_source_df.count()}
        frame = _frame(
            [
                dict(Key="k", DatePartition=data["date"], Score=s)
                for s in data["scores"]
            ],
            "Key string, DatePartition int, Score int",
        )
        out = runner.deterministically_remove_duplicates(
            frame,
            SimpleNamespace(id_cols=["Key"]),
            ["Key", "DatePartition", "Score"],
            ["Score"],
        )
        return {"count": out.count()}
    if stage == "snapshot_latest":
        out = SNAPSHOT["OpportunitiesSnapshotRunner"].get_latest_entry_by_date(
            pd.DataFrame(data["rows"]), ["OpportunityId"], "DatePartition", LOGGER
        )
        return {"markers": sorted(out.Marker.tolist())}
    if stage == "snapshot_replace":
        out = SNAPSHOT["ParquetSnapshotRunner"].resolve_change_data(
            pd.DataFrame(data["prior"]),
            pd.DataFrame(data["changes"]),
            "Hash",
            ["OpportunityId"],
        )
        return {"accounts": sorted(out.AccountId.tolist())}
    if stage == "optional_branch":
        tree = ast.parse(SOURCES["history_job"]["text"])
        cls = next(
            n
            for n in tree.body
            if isinstance(n, ast.ClassDef)
            and n.name == "AccountLevelOpportunitiesHistory"
        )
        method = next(
            n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_run"
        )
        matches = [
            n
            for n in method.body
            if isinstance(n, ast.If)
            and ast.unparse(n.test) == data["dataset"] + " is not None"
        ]
        assert len(matches) == 1 and matches[0].orelse, (
            "expected explicit missing-product branch"
        )
        test = compile(
            ast.Expression(matches[0].test), "pinned_optional_product_predicate", "eval"
        )
        enabled = eval(test, {data["dataset"]: object() if data["present"] else None})
        return {"branch_enabled": enabled, "evidence_tier": "source_predicate_only"}
    if stage in {"core_latest", "core_aggregate"}:
        rows = [
            dict(
                RelationshipGuid="SYN_REL",
                DepositType="ZeroInterestDemand",
                DatePartition=20261001,
                Balance=100.0,
            )
        ]
        if stage == "core_latest":
            rows.append(
                dict(
                    RelationshipGuid="SYN_REL",
                    DepositType="ZeroInterestDemand",
                    DatePartition=20261002,
                    Balance=0.0,
                )
            )
        else:
            rows = rows * data["count"]
        frame = _frame(
            rows,
            "RelationshipGuid string, DepositType string, DatePartition int, Balance double",
        )
        latest = DH.get_latest_entry_by_date(
            frame.filter(F.col("Balance") > 0),
            ["RelationshipGuid", "DepositType"],
            "DatePartition",
            F.rank,
        )
        out = DERIVED["add_summary_columns_to_core_deposits"](latest).collect()
        if stage == "core_latest":
            return {
                "date": out[0].LastRaRunDate,
                "balance": out[0].LastCoreBalancePerDepositType,
            }
        return {"rows": len(out), "balance": out[0].LastCoreBalancePerDepositType}
    if stage == "history_scenario":
        frame = _frame(
            [dict(Marker="candidate", Scenarios=data["array"])],
            "Marker string, Scenarios array<struct<isPipelineScenario:boolean,scenarioType:string>>",
        )
        return {
            "count": HISTORY["get_scenario_level_fields"](
                frame, "Scenarios", [], [("scenarioType", "ScenarioNonPipelineTypes")]
            ).count()
        }
    if stage in {"history_account", "history_empty"}:
        frame = _frame(
            [dict(Marker="candidate", DepositAccounts=data["array"])],
            "Marker string, DepositAccounts array<struct<id:string>>",
        )
        if stage == "history_account":
            out = HISTORY["get_account_level_fields"](
                frame, "DepositAccounts", [], [("id", "AccountId")]
            )
        else:
            out = HISTORY["get_scenarios_with_no_accounts"](frame, ["DepositAccounts"])
        return {"count": out.count()}
    if stage == "treasury":
        row = dict(
            ProductId="SYN_PRODUCT",
            ProductName="Synthetic",
            ServiceCode="SYN",
            ProductFamilyGuid="F",
            EffectiveDate="2026-10-01",
            IsDeleted=False,
            IsEnabled=True,
            ProductAssumptionSetId="A",
            RecurringSettings=[
                dict(
                    Id=dict(Id="P"),
                    UpperRangeLimit=100.0,
                    DefaultUnitPrice=1.0,
                    PerUnitCost=1.0,
                )
            ],
            CostTiers=[dict(Id=dict(Id="C"), PerUnitCost=1.0)],
        )
        row.update(data["patch"])
        schema = (
            "ProductId string, ProductName string, ServiceCode string, ProductFamilyGuid string, EffectiveDate string, IsDeleted boolean, IsEnabled boolean, ProductAssumptionSetId string, "
            "RecurringSettings array<struct<Id:struct<Id:string>,UpperRangeLimit:double,DefaultUnitPrice:double,PerUnitCost:double>>, CostTiers array<struct<Id:struct<Id:string>,PerUnitCost:double>>"
        )
        TREASURY["SparkDatasetDownloader"] = _factory(
            {"TreasuryAssumptions": _frame([row], schema)}
        )
        runner = TREASURY["CoreTreasuryProductAssumptionsData"]()
        runner.source_meta_data, runner.logger = [], LOGGER
        return {"count": runner._run().count()}
    raise ValueError("No upstream evaluator for stage " + stage)
