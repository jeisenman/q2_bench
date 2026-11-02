# Databricks notebook source
"""Exercise optional product routes to the original History account-union boundary."""

from __future__ import annotations


def _default_record(dtype: Any) -> Any:
    """Construct invented values using the pinned source's declared schema."""
    if isinstance(dtype, T.StructType):
        return {field.name: _default_record(field.dataType) for field in dtype.fields}
    if isinstance(dtype, T.ArrayType):
        return []
    if isinstance(dtype, T.MapType):
        return {}
    if isinstance(dtype, T.StringType):
        return "SYN"
    if isinstance(dtype, T.BooleanType):
        return False
    if isinstance(dtype, (T.DoubleType, T.FloatType)):
        return 1.0
    if isinstance(dtype, (T.IntegerType, T.LongType, T.ShortType, T.ByteType)):
        return 1
    if isinstance(dtype, T.TimestampType):
        return datetime(2026, 10, 29, 5)
    if isinstance(dtype, T.DateType):
        return datetime_module.date(2026, 10, 29)
    raise TypeError("Unsupported synthetic schema type: " + str(dtype))


def _schema_field(schema: Any, name: str) -> Any:
    matches = [field for field in schema.fields if field.name.lower() == name.lower()]
    assert len(matches) == 1, (name, schema.fieldNames())
    return matches[0]


def _prune_fixture_type(dtype: Any, paths: list[str]) -> Any:
    """Retain declared types for selected paths; omit only unread input fields."""
    if "" in paths:
        return dtype
    if isinstance(dtype, T.ArrayType):
        return T.ArrayType(
            _prune_fixture_type(dtype.elementType, paths), dtype.containsNull
        )
    assert isinstance(dtype, T.StructType), (dtype, paths)
    groups = {}
    for path in paths:
        head, _, tail = path.partition(".")
        groups.setdefault(head.lower(), []).append(tail)
    fields = []
    for field in dtype.fields:
        if field.name.lower() in groups:
            child = _prune_fixture_type(field.dataType, groups.pop(field.name.lower()))
            fields.append(
                T.StructField(field.name, child, field.nullable, field.metadata)
            )
    assert not groups, ("Selected paths absent from source schema", list(groups))
    return T.StructType(fields)


def _history_input_schema(module: Any, schema: Any) -> Any:
    """Select exactly the nested input fields the original History job reads."""
    accounts = {
        "CommercialLoanAccounts": module.CLA_COLUMNS,
        "DepositAccounts": module.DEPOSIT_COLUMNS,
        "MasterCommitmentLoanAccounts": module.MC_COLUMNS,
        "OtherAccounts": module.OTHER_COLUMNS,
    }
    opp_paths = [
        c[0]
        for c in module.OPPORTUNITY_COLUMNS
        if c[0].lower() not in {"scenarios", "treasuryscenarios", "datepartition"}
    ]
    pricing = [
        c[0]
        for c in module.ALL_SCENARIOS_COLUMNS + module.PRICING_SCENARIOS_COLUMNS
        if c[0].lower() not in {a.lower() for a in accounts}
    ]
    pricing.append("isPipelineScenario")
    for name, columns in accounts.items():
        pricing.extend(
            name + "." + c[0] for c in module.ALL_PRICING_ACCOUNT_COLUMNS + columns
        )
    treasury = [
        c[0]
        for c in module.ALL_SCENARIOS_COLUMNS + module.TREASURY_SCENARIO_COLUMNS
        if c[0].lower() != "treasuryaccounts"
    ] + ["isPipelineScenario"]
    treasury.extend(
        "TreasuryAccounts." + c[0]
        for c in module.ALL_TREASURY_ACCOUNT_COLUMNS
        + module.TREASURY_CASH_MANAGEMENT_COLUMNS
    )
    opp_paths.extend("Scenarios." + p for p in pricing)
    opp_paths.extend("TreasuryScenarios." + p for p in treasury)
    return _prune_fixture_type(schema, ["opportunity." + p for p in opp_paths])


class HistoryUnionCapturedError(Exception):
    """Stop after observing original account construction and identity union."""

    def __init__(self, rows: list) -> None:
        """Retain only synthetic opportunity/account identities."""
        self.rows = rows
        super().__init__("History account union captured")


def _history_rows(module: Any, runner: Any) -> tuple[list, str]:
    """Collect full output or intercept the named account identity boundary."""
    columns = ["OpportunityId", "AccountId", "AccountType"]
    if PAYLOAD.get("history_mode") == "full":
        return runner._run().select(*columns).limit(
            2
        ).collect(), "full_history_transform"
    original_union = module.union_acct_types

    def capture_union(accounts: list, dtypes: list) -> Any:
        """Run the original union on its identity projection, then stop."""
        print("History reached account union", flush=True)
        identity_types = [(name, dtype) for name, dtype in dtypes if name in columns]
        assert {name for name, _ in identity_types} == set(columns)
        out = original_union(accounts, identity_types)
        raise HistoryUnionCapturedError(out.select(*columns).limit(2).collect())

    PATCH_LEDGER.append(
        module.__name__ + ".union_acct_types:identity_projection_capture"
    )
    with patch.object(module, "union_acct_types", capture_union):
        try:
            runner._run()
        except HistoryUnionCapturedError as captured:
            return captured.rows, "original_history_account_union_projection"
    raise AssertionError("History did not reach the account union boundary")


def _history_optional(data: dict) -> dict:
    """Run original account construction against synthetic product datasets."""
    module = MODULES["history_job"]
    metadata = {md.data_source_name: md for md in module.SOURCES_META_DATA}
    target, account = {
        "deposit_products_raw": ("DepositProducts", "DepositAccounts"),
        "commercial_loan_products_raw": (
            "CommercialLoanProducts",
            "CommercialLoanAccounts",
        ),
        "master_commitment_products_raw": (
            "MasterCommitmentProducts",
            "MasterCommitmentLoanAccounts",
        ),
    }[data["dataset"]]
    schema = _history_input_schema(module, metadata["Opportunities"].schema)
    row = _default_record(schema)
    opp_field = _schema_field(schema, "opportunity")
    opp_schema, opp = opp_field.dataType, row[opp_field.name]
    scenario_field = _schema_field(opp_schema, "scenarios")
    scenario_schema = scenario_field.dataType.elementType
    scenario = _default_record(scenario_schema)
    scenario[_schema_field(scenario_schema, "isPipelineScenario").name] = True
    scenario[_schema_field(scenario_schema, "scenarioType").name] = "Alternative"
    account_field = _schema_field(scenario_schema, account)
    scenario[account_field.name] = [_default_record(account_field.dataType.elementType)]
    opp[scenario_field.name] = [scenario]
    frames = {
        "Opportunities": spark.createDataFrame([row], schema),
        "Users": _frame(
            [dict(UserId="SYN", UserOfficerCodes=["SYN"], DatePartition=20261029)],
            "UserId string, UserOfficerCodes array<string>, DatePartition int",
        ),
        "Enumerations": _frame(
            [
                dict(
                    EnumCollectionName="LossGivenDefaultMethod",
                    EnumValue="SYN",
                    EnumDescription="SYN",
                )
            ],
            "EnumCollectionName string, EnumValue string, EnumDescription string",
        ),
    }
    if data["present"]:
        columns = (
            module.DEPOSIT_PRODUCT_COLUMNS
            if target == "DepositProducts"
            else module.LOAN_PRODUCT_COLUMNS
        )
        product_schema = _prune_fixture_type(
            metadata[target].schema, [c[0] for c in columns if c[0] != "DatePartition"]
        )
        frames[target] = spark.createDataFrame(
            [_default_record(product_schema)], product_schema
        )
    HISTORY["SparkDatasetDownloader"] = _factory(frames)
    runner = object.__new__(module.AccountLevelOpportunitiesHistory)
    runner._logger, runner._spark_session = LOGGER, spark
    runner._activity = SimpleNamespace(backfill_flag=False, parameters={})
    runner.filter_date_partitions = None
    rows, tier = _history_rows(module, runner)
    assert len(rows) == int(data["present"]), (target, data["present"], rows)
    if rows:
        assert rows[0].AccountId == "SYN", rows
    return dict(
        branch_enabled=bool(rows),
        evidence_tier=tier,
        rows=len(rows),
        entrypoint="original AccountLevelOpportunitiesHistory._run",
        row_identities=[row.asDict() for row in rows],
    )


_original_evaluate_upstream = _evaluate_upstream


def _evaluate_upstream(case: dict) -> dict:
    """Use imported History account construction; preserve other evaluators."""
    if case["stage"] == "optional_branch":
        return _history_optional(case["data"])
    return _original_evaluate_upstream(case)
