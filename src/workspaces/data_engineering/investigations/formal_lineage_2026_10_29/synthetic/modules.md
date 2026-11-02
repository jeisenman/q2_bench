# Imported-module dataset replay

This extends the earlier AST-isolated run in the same DE Databricks workspace,
`pl-databricks-us-prod-01`, on existing cluster `0901-134744-3vwa15kr`.
The input records are invented; the First Example Bank UUID is a scope label.

The combined replay passed **164/164 checks**: 163 scenarios and the complete
50-column reporting row, with no expected-effect mismatches. See the
[results](modules-results.json), [execution evidence](modules-execution.json),
[comparison with the AST run](modules-comparison.json), and
[Databricks run](https://adb-3510128597187204.4.azuredatabricks.net/?o=3510128597187204#job/746373793441598/run/61721601275456).
All 11 selected source receipts matched; 124 loaded application modules were
verified to come from the pinned source directory. No client data was read and
no application data was written.

The notebook imports unchanged Python modules from these exact commits:

| Repository | Commit |
| --- | --- |
| di-pipelines | `fd9d9b74b53946150a01ed68fb87e4ffa4b7bc1e` |
| di-pyjobs | `32fbfc493d7f039def61c157e579caf24288db48` |
| di-model-server | `7b73b3cdc2b44d29758e5733cf05e7e246dd717d` |

The Go packager retains the import closure and package initializers. It does
not rewrite application source or strip inheritance. Every selected module's
digest must match the existing source receipt. The result also records hashes
of all loaded application modules and rejects imports outside the packaged
source. Fixed third-party import dependencies live in a per-run temporary
driver directory; cluster libraries are not changed.

Runner setup is supplied directly so it cannot connect framework clients.
Monkey patches replace dataset acquisition, storage/path boundaries, the
dispatch clock, explicit exits and uploads. The dataset adapter keeps genuine
source metadata and invokes the original date/version selectors. It follows
the Pandas downloader's empty-read-to-None behavior. Synthetic partition and
version fields are added where the small fixtures omit transport metadata.
All original job calculations and tested helper bodies remain unchanged.

The D2P full-job fixtures invoke the original `DeliveryToPromise.run`, with
each successful run required to reach exactly one captured upload. Early exits
must reach zero uploads. The reporting job then produces the complete literal
50-column golden row. Other scenarios exercise their named original callable
or callable composition; they are not all full end-to-end pipeline replays.

The optional-product fixtures enter the original
`AccountLevelOpportunitiesHistory._run` and execute its account construction.
Source schemas generate invented nested opportunity, account and product
records; fields the job never reads are omitted. At the account-union boundary,
instrumentation calls the original `union_acct_types` with its three identity
columns, collects opportunity/account IDs and account types, and stops before
remaining History formatting. For each of the three product types, a present
product must preserve the candidate account; a missing product must produce no
account row. Their literal branch expectations are unchanged.

These six checks exercise actual data rather than only evaluating a predicate.
They do not validate all History output values or its full output schema.
The full-output attempts were canceled after prolonged execution and did not
produce complete assertion results. They are not counted as passes.

## Reproduce

```bash
go run ./src/workspaces/data_engineering/investigations/formal_lineage_2026_10_29/synthetic/prepare --mode modules
```

Review the retained notebook cells, then use `make_databricks_notebook` and
submit its exact returned SOURCE and digest with `run_databricks_notebook`.
Retrieve the child task's output with the Jobs API and inspect every case,
not only the Databricks lifecycle result.

`--mode imports-probe` checks imports without executing cases.
`--stages report` or `--stages optional_branch` runs a troubleshooting subset.
`--history-mode full` requests the full History output path; that optional mode
has no recorded complete successful replay. The default `account-union` mode
validates the six account-survival effects at the boundary described above.
The golden report assertion is included whenever its full-job fixture is
selected, including when that fixture fails. Subset runs do not claim full
suite coverage.

## Boundaries

Agreement establishes the recorded synthetic expectations under this runtime.
It does not establish correctness for all inputs or approval of implementation
quirks as business rules. Airflow orchestration, actual path discovery, remote
transport/credentials, physical CSV/Parquet persistence, production target
state, remaining History value formatting, and complete upstream RA/HQ execution
remain outside this replay.
Full-graph readiness remains false.

The first imported-module attempt passed 163 of 164 checks. The failing
`report_empty` check exposed an adapter omission: real Pandas downloads
normalize empty data to None before required-input validation. The adapter was
corrected; fixtures, literal expected values and production source were not
changed. See [initial attempt](modules-attempt-01.json).

The repository quality command passed. After the restart dry run, the first
restart attempt found Docker stopped. Docker Desktop was started and the full
MCP rebuild/recreation then completed with healthy services.
