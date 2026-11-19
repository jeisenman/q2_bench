# Local prod-support evidence

Use immutable local evidence if production tasks have since rerun, the user
requests a historical result, or you are preparing a benchmark gold response.
Do not mix a local snapshot with current Airflow discovery.

## September 24, 2026 snapshot

The redacted Airflow dataset is:

```text
~/projects/agentsdk/var/benchmark_data/prod_support/2026-09-24/steps/02-airflow-capture/2026-09-24/airflow_failures.json
```

The dataset has 17 task-instance records with embedded logs. Seven fall in
the `2026-09-24T05:00:00Z` reporting window; ten are prior-day distractors.

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

Parse the selected log in the current agent. Follow
[investigations.md](investigations.md) and
[classifications.md](classifications.md). Do not call live Airflow, Resource
Discovery, or OMS connectors for this reproduction. Keep unresolved identities
and unavailable secondary evidence. Do not mix in current production facts.

The dataset is already redacted. Do not replace it with later-rerun logs. Do
not update expected output until a human reviewer approves the new gold response.
