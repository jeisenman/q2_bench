# Synthetic Delivery to Promise loss cases

The [imported-module replay](modules.md) extends this suite with real job imports,
monkey-patched datasets, captured uploads and account-level History probes. It
uses the same literal fixtures and complete reporting oracle. The AST-isolated
execution below remains separate evidence with its original scope.

This pack replaces the live reporting-date prerequisite with a fixed, entirely synthetic snapshot for First Example Bank (`99b9412b-70fd-4221-8431-d1b3934889ec`). The client UUID is a scope label; every opportunity, relationship, account, amount and storage object is invented. The clock is 2026-10-29T05:00:00Z and the timezone is UTC.

`cases.json` contains 163 scenarios with concrete data and literal expected effects. `golden-report.json` contains the complete expected 50-column report row. A separate final assertion composes the actual D2P and Pandas report methods and compares that full row, including column order, dates, amounts and nulls.

Expected effects distinguish row removal, measure removal with the row retained, superseded versions/accounts, deferred processing, whole-job exit/error, ambiguous selection and client delivery suppression. A surviving opportunity with null core measures is not classified as a lost opportunity. Aggregation is checked for preservation of amount even when it reduces row count.

## Coverage

| Route | Fixtures and control |
| --- | --- |
| As-of selection | Before/equal/after/null dates; DatePartition and WriteTimePartition; non-time-series bypass; Spark and Pandas |
| Version selection | Wrong major, older minor, explicit minor absent/present, ties, nullable keys, lexical 1.9 versus 1.10 behavior |
| Opportunity eligibility | Positive/zero/negative/null promises, status, deletion flag, scenario type, missing/empty relationship ID |
| Close-date scope | Today, future, 1095/1096/1097-day boundaries, null and malformed dates |
| Ranking | Latest record, rank ties preserved, row_number ties classified as ambiguous |
| Account contributions | Non-deposit/null account type; matured, same-day and null CD maturity/pricing; unknown and mapped treasury product types |
| Core contributions | Positive/zero/negative/null balances, positive filtering before latest selection, sum preservation for repeated contributions |
| Time windows | History lookback boundary; close date and upper bounds for 6/12/24/36 fixed 30-day windows; zero weighting |
| Enrichment | Missing owner, empty Users/Regions, unmatched relationship and unmatched core data retain the opportunity through left joins |
| Snapshots | Older opportunity save removed, every account in latest save retained, prior accounts replaced at opportunity grain |
| Incremental RA | Unchanged/changed/null run IDs, removed primary run, partition cap, rerun excludes new dates, legacy dedup, null partition, duplicate validation |
| Upstream history | Empty/null scenario/account arrays, rejected scenario types, no-account fallback, optional product branch predicates |
| Treasury assumptions | Deleted/null-deletion rows, empty/null recurring settings and cost tiers removed by explode |
| Whole D2P job | Missing required input, all-zero core data, no eligible opportunities and global stale-core guard |
| Pandas reporting | Correct date formatting, nullable date retained, float/malformed date fails, empty/missing input exits |
| Output casting | Valid cast, invalid value becomes null with ANSI off, invalid value fails with ANSI on, absent projected column fails |
| Dispatch | Recent/exactly-48h/older clock, backfill, missing client storage, zero/multiple source files |

The six optional-product probes execute the actual AST condition and inspect its explicit missing-input branch. They are marked `source_predicate_only`; they do not execute the complete nested opportunity-history transformation. Other cases execute named original functions/methods or small compositions of them. `coverage.json` maps stages to source evidence and case IDs.

## Execution boundary

The notebook parses exact pinned source bytes, checks their SHA256 values, and compiles only listed function/method definitions and literal constants. It omits application imports and strips unrelated class initialization. Production downloaders, uploaders, path construction, client storage and clock are replaced with isolated fixture-backed objects. Source date/version selectors are exercised independently; the full-job fixture receives frames that have already been selected.

All Spark/Pandas computation runs in Databricks. No client dataset is read, no application upload method is called, and the dispatch sink is a Python dictionary. Synthetic runs use a new Spark session with UTC, two shuffle partitions and ANSI off; a dedicated casting case enables ANSI only within a restored scope. Runtime versions are retained in the result.

The source pins remain the investigation's di-pipelines and di-pyjobs commits. This validates known loss routes in the inspected standard D2P slice; it does not establish whole-repository branch coverage. Actual Airflow scheduling/trigger behavior, physical path discovery, CSV/ADLS persistence, remote transport failures and complete upstream History/HQ implementations remain separate validation boundaries. Case outcomes must not be promoted to a full production replay claim.

## Reproduce

Prepare the immutable source bundle from the repository root:

```bash
go run ./src/workspaces/data_engineering/investigations/formal_lineage_2026_10_29/synthetic/prepare
```

The Go command reads source blobs at full commits and rejects digest changes. It writes the generated notebook under the operating system's temporary directory in `qtwo-d2p-synthetic/notebook.py`; it never executes Python locally. Individual retained notebook modules are under 400 lines. The temporary combined SOURCE bundle is a generated execution artifact.

Review the packaged code and pass it to the existing `make_databricks_notebook` tool with platform `data_engineering`. Verify that the returned SOURCE only adds the comment wrapper and retain its source_sha256. Submit that exact SOURCE through `run_databricks_notebook` with an approved existing cluster and a bounded timeout.

Retrieve the child task output through the Databricks Jobs API. Inspect the JSON result's status, failed count and every failure; a Databricks lifecycle SUCCESS alone is insufficient because the notebook returns structured failure evidence too. Source/runtime errors fail cases and remain visible. The complete report comparison has a separate result entry.

## Recorded AST-isolated execution

All 164 checks passed on Databricks: 163 scenarios plus the complete 50-column report comparison. The runtime was Spark 4.1.0 with Pandas 2.2.3. [Results](results.json) retain each observed outcome; [execution evidence](execution.json) records notebook/source hashes, fixture hashes, cluster, parent/child run IDs and the earlier harness correction. The six optional-product cases remain explicitly marked as predicate probes.

The [successful run](https://adb-3510128597187204.4.azuredatabricks.net/?o=3510128597187204#job/116881781425574/run/916624163559760) used synthetic in-memory inputs only. An initial execution exposed a missing StringType binding in the extraction harness; that binding was corrected without changing fixtures, expected values or production source. The full suite then passed. Full physical/orchestration coverage remains excluded as described above.

## Interpreting outcomes

The fixture oracle describes the pinned implementation's expected behavior. It does not automatically endorse each behavior as a business rule. In particular, lexical minor-version ordering, selection of an older positive core value after a newer zero is filtered out, fixed 30-day month windows and ambiguous row_number survivors deserve review. Keep an observed match separate from acceptance of that rule.

Full-row prediction is only claimed for the literal synthetic golden case when its complete comparison passes. Every other scenario asserts its explicitly named effect or projection. Results and exact run/source identities are recorded separately after execution.
