# Databricks cloud-only integration testing

Reviewed: 2026-09-30

Use this procedure when a repository or worktree prohibits local Python,
local containers, Chrome, and Playwright. Local commands may inspect source,
prepare a zip archive, and call supported CLIs. Python execution and
behavioral validation occur only in Databricks.

## Operating rules

- Use the native Databricks CLI or REST APIs for workspace, DBFS, clusters,
  jobs, and run output.
- Review every notebook's exported source before running it.
- Pin the client ID, window start, environment, and target records.
- Keep production-backed validation read-only. Use the integration helper's
  intercepted upload instead of writing an output dataset.
- Never print private package indexes, tokens, secrets, or full production
  datasets. Return bounded diagnostic rows.
- Treat cluster/bootstrap failures separately from application failures.

## Package and notebook flow

The `di-pipelines` integration helper expects an archive named:

```text
dbfs:/FileStore/jars/000_datascience_jobs-<ticket>.zip
```

The archive must contain `datascience_jobs/` at its root. If local Python is
prohibited, create the archive with a standard zip utility and upload it with:

```bash
databricks fs cp /tmp/000_datascience_jobs-<ticket>.zip \
  dbfs:/FileStore/jars/000_datascience_jobs-<ticket>.zip --overwrite
```

Import reviewed Databricks source without a browser:

```bash
databricks workspace import <workspace-path> \
  --file <notebook-source.py> --format SOURCE \
  --language PYTHON --overwrite
```

Submit through `databricks jobs submit`, using either an approved existing
cluster or an ephemeral job cluster. Save both the parent run ID and task run
ID; `jobs get-run-output` requires the task run ID.

## Integration notebook pattern

Follow the repository template used by
`/Shared/Data-Science/DI-Pipelines/Integration-Testing/DE-2846`:

1. Load `Integration-Testing-Path-Helpers`.
2. Resolve the uploaded archive with `get_import_path(ticket)`.
3. Put that archive first on the Python path.
4. Load the integration global variables.
5. Call `run_integration_test` with pinned activity parameters.
6. Extract and inspect the intercepted output.

For `BaseMetaDataRunner`, the intercepted upload commonly returns a
`DatasetUploader` in `out["args"][0]`, not a DataFrame in
`out["kwargs"]["dataframe"]`. Read the assigned DataFrame from the uploader's
`outputs_meta_data` collection.

## Runtime dependencies

Do not assume a running cluster still has repository dependencies after a
restart. Check the runtime and attached libraries first.

The production integration configuration historically targets older
Databricks runtimes. A newer DBR 18/Python 3.12 cluster may lack `di_pyjobs`
and other eagerly imported packages. Prefer a current approved wheel already
stored in Databricks over a private-index install. On 2026-09-30, the current
artifact was:

```text
dbfs:/FileStore/jordan.eisenman/di_pyjobs/di_pyjobs-0.1.13-py3-none-any.whl
```

Install test-only dependencies into a notebook/driver-scoped target. Do not
modify a shared cluster's library configuration merely to unblock one test.
If an unrelated optional dependency is eagerly imported but unused by the
target job, a narrow notebook-only stub may be acceptable; document it and
never change application behavior to accommodate the test harness.

## BKU Delivery to Promise example

The BankUnited DV validation used:

```text
Client ID: f8ebcaa4-3f60-4f6e-8fa5-5b16c23032cb
Window start: 2026-09-18T05:00:00Z
Archive ticket: BKU-FIX
```

The notebook tested two theories:

- Deposits: derive `TreasuryHybrid` as the nonnegative residual of
  `AllDepositBalance` after the three standard D2P deposit buckets.
- Other products: aggregate and join core income by direct `RelationshipId`
  rather than `TopLevelParentRelationshipId`.

Use remote Spark fixture assertions before client data, then assert bounded
client outcomes. For this case, Westchester General Hospital should expose a
`TreasuryHybrid` core balance of `23062.13`, and Brokers Title should expose
relationship-level core other income. Delivery-window maximums may remain
null when the latest RA partition predates the opportunity close date.

## Failure triage

- `ModuleNotFoundError: di_pyjobs`: cluster bootstrap/runtime issue.
- Private index reports no distributions: use an approved Databricks-resident
  wheel or repair the cloud package configuration; do not fall back to local
  execution.
- `KeyError: dataframe` after several minutes: the jobs may have succeeded;
  inspect the intercepted positional `DatasetUploader`.
- Application assertion failure: capture the target rows, source partition
  dates, relationship keys, and product types before changing code.
