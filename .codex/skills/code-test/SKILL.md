---
name: code-test
description: Test data-engineering changes by finding qualifying source data, running bounded validation loops, and recording PR evidence after deployment.
---

# Code Testing

Use when implementation is ready for test-data selection and behavioral
validation.

This skill does not plan, trigger, approve, poll, retry, or verify deployments.
When testing requires deployed DAG or job code, load and follow the `deploy`
skill for the exact repository, commit, and environment. Resume this workflow
only after `deploy` reports that every required stage succeeded.

## Finding Testing Data

Use this workflow to find Alpha source data that can be brought downstream for
the job or fields being changed:

1. Run the static candidate index first:

   ```bash
   uv run python .codex/skills/code-test/scripts/alpha_data_candidates.py \
     --repository <di-pipelines> \
     --contx-alpha <di-scheduling>/Deployment/ContxMetadata/alpha \
     --field <new-field>
   ```

   It reads Git and Python source only, follows extracted `job_reference`
   values, reports likely datasets, versions, formats and paths, checks field
   occurrences, auto-detects `main` or `master`, and shortlists safe Alpha
   Contx storage metadata. Review its JSON before making any remote call.
2. Trace each changed DAG task through its `job_reference` to the job's primary
   input dataset, version, format, and required new fields. Do not substitute a
   downstream copy or data from another system for the primary dataset.
3. Use `lookup_contx_resources` to confirm the script's Alpha Contx shortlist
   for
   the client and shortlist only storage or DataLake resources that can contain
   those primary datasets.
4. Use `lookup_azure_resources` for the relevant Alpha resource group. If it
   returns `login_required` or `subscription_access_required`, run the exact
   returned `az login` command, or ask the user to complete it, before retrying.
5. Search the shortlisted accounts for the dataset names and paths declared by
   the changed jobs. Prefer client
   `99b9412b-70fd-4221-8431-d1b3934889ec` because its test data is consistent
   across environments.
6. Use the remote-data MCP to generate a bounded read-only notebook, or run the
   repository's approved read-only discovery script. Temporarily download only
   the smallest relevant file or partition into an ignored temporary directory.
7. Inspect its schema and bounded counts. A candidate qualifies only when the
   primary dataset contains every new field and each new field has at least one
   non-null value. An absent or all-null field fails the data standard.
8. Record the client, environment, datastore, primary dataset, partition,
   field names, row count, and non-null counts. Delete temporary downloads
   after recording the evidence.

If no Alpha candidate qualifies, record the negative Alpha evidence, then run
the same bounded candidate search in staging. Re-run the static index with the
staging Contx metadata and `--environment staging`, then repeat the Contx,
Azure, and bounded schema/non-null checks. Report staging results separately;
staging data is a proposed test candidate, not Alpha evidence. Do not silently
switch environments.

```bash
uv run python .codex/skills/code-test/scripts/alpha_data_candidates.py \
  --repository <di-pipelines> \
  --contx-alpha <di-scheduling>/Deployment/ContxMetadata/staging \
  --environment staging \
  --field <new-field>
```

## Finding Production Data

If staging also lacks qualifying non-null data, read
[Databricks field-flow validation](references/databricks-field-flow.md). Use
production Contx stores only for bounded, read-only discovery of clients whose
primary upstream dataset contains the field with non-null values.

Use the remote-data MCP to generate and run the reviewed
`scripts/de_notebook.py` template:

- use Data Engineering Databricks for production source discovery;
- use RA Databricks only when tracing an RA source or transformation requires
  the RA workspace;
- follow the changed DAG task through `job_reference` and dataset declarations
  before choosing either target.

After finding a representative production candidate, call
`upload_databricks_integration_branch` for `master` and the selected
`RA-####` branch. Run identical bounded inputs through both versions and
compare row/key counts, schemas, dropped or duplicate rows, and per-field
non-null counts.

When natural integration data cannot exercise the field, monkey patch only the
notebook-local input DataFrame using bounded production-derived values. Assert
that row and distinct-key counts are unchanged, never persist the patched
input, and report the result as synthetic flow evidence rather than natural
Alpha or staging evidence.

## Deployment handoff

Give the `deploy` skill the exact repository, branch or commit, target
environment, changed paths, and expected post-deployment check. It owns
`deployment.md`, deployment scope, Azure execution, approvals, stage polling,
retries, and deployment completion evidence.

After deployment succeeds, use the completion timestamp to select a new
Airflow run and continue testing here. Databricks branch uploads used only for
bounded notebook comparisons remain test setup rather than an environment
deployment.

## Loop Testing

Loop testing supports two targets:

- Alpha for deployed DAG and job validation;
- Databricks for bounded branch comparison or notebook-local synthetic input
  testing.

Start both loops by finding qualifying test data and recording why it exercises
the changed behavior.

### Alpha loop

For every commit that is ready to test:

1. Load and invoke `deploy` with the exact commit and Alpha environment.
2. Wait for `deploy` to report every required stage successful for that commit.
3. Select an Airflow run that started after deployment completed.
4. Run the smallest producer job that exercises the change and poll it to a
   terminal state.
5. Validate the downstream dataset, including schema, row and key counts, and
   non-null counts for every new field.
6. On failure, collect the exact deployment, run, task, logs, and input
   evidence before changing code.
7. Apply the smallest supported fix and run local static and unit checks.
8. Commit and push the fix, then invoke `deploy` again for the new commit.

Never reuse a successful deployment from an earlier commit. Continue calling
`deploy` whenever a new Alpha-testable commit is ready until validation passes
or the stop condition is reached.

### Databricks loop

For every commit that is ready to compare:

1. Upload the exact branch commit through the approved remote-data workflow.
2. Run identical bounded inputs through the baseline and branch archives.
3. Poll the submitted runs to terminal states.
4. Compare row and key counts, schemas, dropped or duplicate rows, and relevant
   non-null counts.
5. On failure, collect the exact archive commits, notebook runs, logs, and input
   evidence before changing code.
6. Apply the smallest supported fix and run local static and unit checks.
7. Commit and push the fix, upload the new commit, and repeat the comparison.

Do not invoke `deploy` for a notebook-only Databricks comparison unless the
test also requires an environment deployment.

Keep each iteration tied to its commit, environment, input partition, and run
ID. Do not reuse evidence from an earlier commit as proof for a later one.
Stop when the expected downstream result passes, the user declines another
external mutation, or progress requires a new decision or credential.


# Alpha validation

Use Alpha to validate branch behavior with bounded source-data evidence and an
exact downstream rerun plan.

Before this workflow, use `deploy` to create `deployment.md`, determine the
component stages, deploy the exact branch commit, and record successful stage
completion times. Continue only with an Airflow run that started after every
required deployment stage completed.

Every Airflow clear requires a reviewed dry-run selection and explicit
approval for the exact DAG, run, and tasks.

## Testing new fields in di-pipelines

Use this workflow when a `di-pipelines` branch adds or changes dataset fields.

### 1. Find non-null source evidence

Load and follow the `remote-data` skill for the approved, read-only Databricks
workflow.

Trace the source from declarations rather than guessing its path:

1. Find the active DAG task and follow its `job_reference`.
2. Read the resource, path convention, file name, format, and dataset version.
3. Resolve the Alpha client partition and datastore from `di-scheduling`.
4. Pin one client and a bounded UTC window.
5. Generate and review a read-only Databricks SOURCE notebook.
6. Retain the generated `source_sha256`.
7. Run the exact source on an approved existing cluster.
8. Retrieve bounded JSON evidence through the Jobs API.

Aggregate by run date and return:

- total row count;
- non-null count for every new field;
- non-zero count when zero differs from missing;
- source file count;
- Databricks parent and task run IDs.

Use this aggregation pattern after deriving the exact input frame:

```python
from pyspark.sql import functions as F

aggregates = [F.count(F.lit(1)).alias("row_count")]
for field in FIELDS:
    populated = F.col(field).isNotNull() & (F.trim(F.col(field)) != "")
    aggregates.extend(
        [
            F.sum(F.when(populated, 1).otherwise(0)).alias(f"{field}__non_null"),
            F.sum(F.when(F.col(field).cast("double") != 0.0, 1).otherwise(0)).alias(
                f"{field}__non_zero"
            ),
        ]
    )

daily = frame.groupBy("_run_date").agg(*aggregates).orderBy("_run_date")
```

Choose a date where every required field has at least one non-null row. If no
date qualifies, stop and distinguish:

- no run files in the window;
- missing client directory;
- fields absent from the source schema;
- fields present but null;
- upstream deployment or data-generation failure.

Do not rerun downstream tasks without suitable source evidence.

### 2. Record source evidence

Write exact counts and dates to `deployment.md`:

```markdown
| Field | Run date | Rows | Non-null | Non-zero | Notes |
|---|---|---:|---:|---:|---|
| NewBalance | 2026-09-23 | 155 | 155 | 10 | Source CSV v1.3 |
```

Also record:

- resolved ADLS path pattern without credentials;
- client ID and UTC window;
- Databricks parent and task run IDs;
- whether every row or only some rows populated each field;
- schema drift between run files.

The evidence must support the rerun decision without exposing raw rows.

### 3. Plan and approve the recursive downstream rerun

Identify the exact producer task in the post-deployment Alpha DAG run.
Preserve task-group prefixes, for example:

```text
ra_group.get_relationship_aggregate_balances
```

Dry-run Airflow's clear-task API with:

```json
{
  "dag_run_id": "<dag-run-id>",
  "task_ids": ["<fully-qualified-producer-task-id>"],
  "dry_run": true,
  "include_downstream": true,
  "include_upstream": false,
  "include_future": false,
  "include_past": false,
  "only_failed": false,
  "only_running": false,
  "reset_dag_runs": true
}
```

`include_downstream=true` recursively selects descendants.
`only_failed=false` is intentional for this Alpha workflow because previously
successful consumers may need recomputation with the new fields.

Before execution:

1. Verify the producer task used the newly deployed code.
2. Review every task returned by the dry run.
3. Exclude unrelated report, delivery, or client tasks.
4. Record the selection in `deployment.md`.
5. Request explicit approval for the exact DAG, run, starting task, and
   downstream selection.

After approval, repeat the identical request with `dry_run=false`. Never add
upstream, past, or future runs. Monitor all selected tasks to terminal states
and record their outcomes and relevant failed-task logs in `deployment.md`.

## Completion criteria

The test is complete when:

- the `deploy` skill recorded the exact commit and successful required stages;
- the selected DAG run started after deployment;
- remote-data evidence proves the fields are present and non-null;
- the recursive downstream selection was reviewed and approved;
- rerun outcomes are recorded.

## PR Comment
