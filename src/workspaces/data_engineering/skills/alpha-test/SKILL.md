---
name: alpha-test
description: Plan and execute evidence-backed Alpha validation for data-engineering branch changes. Use when testing new or changed di-pipelines fields, deciding which DAG/de-jobs/ds-jobs artifacts must deploy, recording deployment evidence, or approval-gating recursive downstream Airflow reruns.
---

# Alpha Test

Use Alpha to validate branch behavior with a documented deployment scope,
bounded source-data evidence, and an exact downstream rerun plan.

Do not trigger a deployment or clear Airflow tasks unless the user has
authorized that external mutation. Every Airflow clear requires a reviewed
dry-run selection and explicit approval for the exact DAG, run, and tasks.

## Testing new fields in di-pipelines

Use this workflow when a `di-pipelines` branch adds or changes dataset fields.

### 1. Create or update deployment.md

Before deploying, add `deployment.md` at the root of the feature branch.
Record the intended test before collecting results:

```markdown
# Alpha deployment

## Change

- Branch:
- Commit:
- Dataset:
- Dataset version:
- New or changed fields:
- Expected producer task:
- Expected downstream consumers:

## Deployment scope

- [ ] DAGs
- [ ] de-jobs
- [ ] ds-jobs

## Alpha deployment evidence

| Component | Required | Pipeline stage | Status | Completed UTC |
|---|---:|---|---|---|
| DAGs |  | Alpha DAGs |  |  |
| de-jobs |  | alpha_de_jobs |  |  |
| ds-jobs |  | alpha_ds_jobs |  |  |

## Source-data evidence

- Environment: Alpha
- Client ID:
- UTC window:
- RA run path:
- Databricks parent run ID:
- Databricks task run ID:

| Field | Run date | Rows | Non-null | Non-zero | Notes |
|---|---|---:|---:|---:|---|

## Airflow rerun

- DAG ID:
- DAG run ID:
- Starting task ID:
- Dry-run selection:
- Approval reference:
- Final task states:
```

Do not put credentials, customer names, or unbounded production-backed rows in
`deployment.md`.

### 2. Determine deployment scope

Inspect the branch diff and active DAG references:

```bash
git diff --name-only <target-branch>...HEAD
rg -n -C 12 "<dataset-or-task-name>" \
  dags/precisionlender/dags/
```

Map changed areas to Alpha stages:

| Changed area | Required Alpha stage |
|---|---|
| `dags/` or `dag-utils/` | `Alpha DAGs` |
| `de-jobs/` | `alpha_de_jobs` |
| `ds-jobs/` | `alpha_ds_jobs` |

Select every applicable stage. A field change can require all three when the
ingestion contract, dataset metadata or consumers, and DAG parameters or
dependencies change together.

The jobs stages have these prerequisites:

```text
build_de_jobs -> feed_publish_de_jobs -> alpha_de_jobs
build_ds_jobs -> feed_publish_ds_jobs -> alpha_ds_jobs
Alpha DAGs
```

If deployment is authorized, trigger the branch pipeline and wait for every
required Alpha stage to report success. Pipeline submission, artifact
creation, or approval alone is not completion.

Record each successful stage and completion time in `deployment.md`. Select a
DAG run that started after all required deployments completed; an already
running task can retain previously loaded code or configuration.

### 3. Find non-null source evidence

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
            F.sum(F.when(populated, 1).otherwise(0)).alias(
                f"{field}__non_null"
            ),
            F.sum(
                F.when(F.col(field).cast("double") != 0.0, 1).otherwise(0)
            ).alias(f"{field}__non_zero"),
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

### 4. Record source evidence

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

### 5. Plan and approve the recursive downstream rerun

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

- `deployment.md` records the change and test scope;
- every required Alpha deployment succeeded;
- the selected DAG run started after deployment;
- remote-data evidence proves the fields are present and non-null;
- the recursive downstream selection was reviewed and approved;
- rerun outcomes are recorded.

## PR Comment
