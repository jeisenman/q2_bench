# Local prod-support evidence

Use immutable local evidence when production tasks have since been rerun, when
the user asks to reproduce a historical result, or when producing a benchmark
gold response. Do not mix a local snapshot with current Airflow discovery.

## September 24, 2026 snapshot

The redacted Airflow dataset is:

```text
~/projects/agentsdk/var/benchmark_data/prod_support/2026-09-24/steps/02-airflow-capture/2026-09-24/airflow_failures.json
```

It contains 17 task-instance records and embedded logs. Seven records are in
the `2026-09-24T05:00:00Z` reporting window and ten are prior-day distractors.

Set a shell variable before analysis:

```bash
PROD_SUPPORT_DATASET="$HOME/projects/agentsdk/var/benchmark_data/prod_support/2026-09-24/steps/02-airflow-capture/2026-09-24/airflow_failures.json"
```

List the captured task identities without printing logs:

```bash
jq -r '.records[] |
  [.region, .dag_id, .run_id, .task_id, .try_number, .start_at, .end_at] |
  @tsv' "$PROD_SUPPORT_DATASET"
```

Retrieve one exact captured log:

```bash
jq -r --arg dag_id '<dag-id>' --arg run_id '<run-id>' \
  --arg task_id '<task-id>' \
  '.records[] |
   select(.dag_id == $dag_id and .run_id == $run_id and
          .task_id == $task_id) |
   .log' "$PROD_SUPPORT_DATASET"
```

Parse the selected log in the current agent using
[investigations.md](investigations.md) and
[classifications.md](classifications.md). Do not call live Airflow, Resource
Discovery, or OMS connectors while reproducing the snapshot. Preserve
unresolved identities and unavailable secondary evidence rather than mixing
current production facts into the historical result.

The dataset is already redacted. Do not replace it with logs from a later
rerun, and do not update expected output until a human reviewer explicitly
approves the new gold response.
