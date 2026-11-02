# Databricks notebook source
"""Run actual job methods with synthetic frames and intercepted I/O."""

from __future__ import annotations


def _full_inputs(mode: str) -> dict:
    """Construct the five direct D2P inputs with explicit primitive schemas."""
    names = list(
        dict.fromkeys(
            [x[0] for x in DERIVED["OPPORTUNITY_COLUMNS"] + DERIVED["ACCOUNT_COLUMNS"]]
            + ["AccountType"]
        )
    )
    numbers = {
        n
        for n in names
        if any(
            x in n
            for x in [
                "Roe",
                "Equity",
                "Balance",
                "Commitment",
                "Income",
                "DepositAmount",
            ]
        )
    }
    row = {n: 1.0 if n in numbers else "SYN_" + n for n in names}
    row.update(
        OpportunityId="SYN_OPP",
        RelationshipId="SYN_REL",
        OwnerId="SYN_OWNER",
        OpportunityName="SYN_OPPORTUNITY",
        OwnerName="SYN_OWNER",
        OwnerEmail="owner@example.invalid",
        CreatedDate="2026-08-01",
        PricingDate="2026-08-01",
        CloseDate="2026-09-01",
        LastModified="2026-10-02 13:00:00",
        OpportunityIsDeleted=False,
        ScenarioType="Pipeline",
        OpportunityStageStatus="InOrigination" if mode == "opps_zero" else "ClosedWon",
        OpportunityDepositAverageBalance=100.0,
        OpportunityOtherIncome=0.0,
        OpportunityLoanCommitment=1000.0,
        AccountType="Deposit",
        DepositAmount=100.0,
        DepositProductType="ZeroInterestDemand",
        CdTerm=12,
        CdOriginationDate="2026-01-01",
    )
    types = {n: "double" if n in numbers else "string" for n in names}
    types.update(OpportunityIsDeleted="boolean", CdTerm="int")
    accounts = _frame([row], ", ".join(n + " " + types[n] for n in names))
    users = _frame(
        [
            dict(
                UserId="UNMATCHED" if mode == "owner_missing" else "SYN_OWNER",
                UserHomeRegionId="SYN_REGION",
                DatePartition=20261001,
            )
        ],
        "UserId string, UserHomeRegionId string, DatePartition int",
    )
    if mode == "empty_users":
        users = users.limit(0)
    regions = _frame(
        [
            dict(
                RegionId="SYN_REGION",
                RegionName="SYN_OWNER_REGION",
                DatePartition=20261001,
            )
        ],
        "RegionId string, RegionName string, DatePartition int",
    )
    if mode == "empty_regions":
        regions = regions.limit(0)
    balance = {x[0]: 0.0 for x in DERIVED["REL_AGG_BALANCES_COLS"]}
    balance.update(
        RelationshipNewId="SYN_REL",
        DatePartition=20260930 if mode == "stale" else 20261001,
        ZeroInterestDepositBalance=0.0 if mode == "core_zero" else 100.0,
    )
    if mode == "missing_core_match":
        balance["RelationshipNewId"] = "UNMATCHED"
    schema = ", ".join(
        n
        + (
            " string"
            if n == "RelationshipNewId"
            else " int"
            if n == "DatePartition"
            else " double"
        )
        for n in balance
    )
    balances = _frame([balance], schema)
    relationship = {x[0]: "SYN_" + x[0] for x in DERIVED["RELATIONSHIPS_COLS"]}
    relationship.update(
        RelationshipId="SYN_REL",
        RelationshipName="SYN_RELATIONSHIP",
        OwnerName="SYN_REL_OWNER",
        RegionName="SYN_REL_REGION",
        OwnerEmail="relationship@example.invalid",
        StrategicRoe=0.12,
        FtpRoe=0.08,
        DatePartition=20261001,
    )
    if mode == "missing_relationship":
        relationship["RelationshipId"] = "UNMATCHED"
    schema = ", ".join(
        n
        + (
            " int"
            if n == "DatePartition"
            else " double"
            if n in {"StrategicRoe", "FtpRoe"}
            else " string"
        )
        for n in relationship
    )
    return dict(
        AccountLevelOpportunitiesSnapshot=accounts,
        Users=users,
        Regions=regions,
        RelationshipAggregateBalances=balances,
        Relationships=_frame([relationship], schema),
    )


GOLDEN = None


def _full_job(data: dict) -> dict:
    """Run the pinned D2P method on preselected memory inputs, never an uploader."""
    global GOLDEN
    mode = data["mode"]
    DERIVED["SparkDatasetDownloader"] = _factory(_full_inputs(mode), mode == "missing")
    runner = DERIVED["DeliveryToPromise"]()
    runner.source_meta_data, runner.logger = [], LOGGER
    runner.activity = SimpleNamespace(window_start_date_partition=20261029)
    try:
        frame = runner._run()
        if mode == "golden":
            frame = frame.cache()
        rows = frame.collect()
    except FixtureExit:
        return {"outcome": "exit"}
    if mode == "golden":
        GOLDEN = frame
    first = rows[0] if rows else None
    return dict(
        outcome="rows",
        count=len(rows),
        deposit=first.OppDepositsPromised if first else None,
        core=first.LastCoreBalancePerDepositType if first else None,
        average6=first.AvgBalance6 if first else None,
        owner_region=first.OpportunityOwnerRegion if first else None,
    )


def _report(data: dict) -> dict:
    """Execute report formatting with typed Pandas inputs and no file writer."""
    row = {old: 1.0 for old, _ in REPORT["FINAL_COLS"]}
    row.update(
        OpportunityId="SYN_OPP",
        OpportunityLastModified="2026-10-02 13:00:00",
        LastRaRunDate=data["value"],
    )
    pdf = pd.DataFrame([row])
    pdf["LastRaRunDate"] = pd.array(pdf.LastRaRunDate, dtype=data["dtype"])
    if data.get("empty"):
        pdf = pdf.iloc[0:0]
    REPORT["PandasDatasetDownloader"] = _factory(
        {"DeliveryToPromiseData": pdf}, data.get("missing", False)
    )
    REPORT["SOURCE_MD"] = []
    runner = REPORT["DeliveryToPromise"]()
    runner.logger = LOGGER
    try:
        out = runner.run()
        return dict(
            outcome="rows",
            count=len(out),
            columns=len(out.columns),
            date=out.iloc[0]["Last RA Run Date"],
        )
    except FixtureExit:
        return dict(outcome="exit")
    except (ValueError, TypeError) as error:
        return dict(outcome="error", error_type=type(error).__name__)


class _MemoryFile(io.BytesIO):
    """Capture dispatch bytes inside the process only."""

    def __init__(self, store: dict, path: str, writing: bool) -> None:
        super().__init__(b"synthetic\n" if not writing else b"")
        self.store, self.path, self.writing, self.size = store, path, writing, 10

    def close(self) -> None:
        if self.writing and not self.closed:
            self.store[self.path] = self.getvalue()
        super().close()


class _MemoryADLS:
    """Replace all ADLS calls with an isolated in-memory dictionary."""

    def __init__(self, files: int) -> None:
        self.files, self.store = files, {}

    def glob(self, path: str) -> list[str]:
        return ["synthetic-" + str(i) for i in range(self.files)]

    def open(self, path: str, mode: str) -> _MemoryFile:
        return _MemoryFile(self.store, path, mode == "wb")

    def exists(self, path: str) -> bool:
        return path in self.store

    def remove_file(self, path: str) -> None:
        self.store.pop(path)


def _dispatch(data: dict) -> dict:
    """Execute dispatch's original gates while replacing clock, paths and storage."""
    source, target = _MemoryADLS(data.get("file_count", 1)), _MemoryADLS(0)
    clock = datetime(2026, 10, 29, 5, tzinfo=timezone.utc)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return clock

    def resource(name: str) -> SimpleNamespace:
        if name == "output" and data.get("no_resource"):
            raise ValueError("synthetic absent resource")
        return SimpleNamespace(name=name)

    def path(kind: str) -> Any:
        return lambda **kw: SimpleNamespace(
            to_activity_context_path=lambda: SimpleNamespace(fully_qualified=kind)
        )

    extra = dict(
        datetime=FrozenDateTime,
        os=os,
        parse_datafactory_datestring=lambda datestring: datetime.fromisoformat(
            datestring
        ),
        key=SimpleNamespace(
            **{
                k: k
                for k in [
                    "WINDOW_START",
                    "INPUT_RESOURCE",
                    "INPUT_FILESYSTEM",
                    "OUTPUT_RESOURCE",
                    "OUTPUT_FILESYSTEM",
                    "INPUT_FILENAME",
                    "OUTPUT_FILENAME",
                ]
            }
        ),
        adls=SimpleNamespace(
            new_client=lambda resource, filesystem: (
                source if resource.name == "input" else target
            ),
            FILE_NOT_FOUND_EXCEPTIONS=(FileNotFoundError,),
        ),
        DataStudioLibraryHistoricalV2=path("source"),
        DataStudioLibraryClientV2=path("history"),
        DataStudioLibraryClientLatestV2=path("latest"),
        MoreThanOneDatafeedRecord=ValueError,
    )
    namespace = _load(
        "dispatch_job", [], {"DispatchL3LibraryDatafeedsV2": ["run"]}, extra
    )
    runner = namespace["DispatchL3LibraryDatafeedsV2"]()
    runner.logger, runner.jobname, runner.context = (
        LOGGER,
        "synthetic",
        SimpleNamespace(get=resource),
    )
    params = dict(
        WINDOW_START=(clock - timedelta(hours=data["age_hours"])).isoformat(),
        INPUT_RESOURCE="input",
        INPUT_FILESYSTEM="synthetic",
        OUTPUT_RESOURCE="output",
        OUTPUT_FILESYSTEM="synthetic",
        INPUT_FILENAME="*.csv",
        OUTPUT_FILENAME="record.csv",
    )
    runner.activity = SimpleNamespace(
        parameters=params,
        backfill_flag=data.get("backfill", False),
        client_id=FIXTURE["client_id"],
        run_id="SYNTHETIC",
        dataset_pathname="DeliveryToPromise",
        dataset_version="v2.2",
        window_start_timestamp=0,
    )
    try:
        runner.run()
        return dict(outcome="written", writes=len(target.store))
    except FixtureExit:
        return dict(outcome="exit", writes=len(target.store))
    except ValueError as error:
        return dict(
            outcome="error", writes=len(target.store), error_type=type(error).__name__
        )
