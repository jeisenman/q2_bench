# Investigation contracts

## Luna delegation

Delegate each independent, read-only failure investigation to
`openai.gpt-5.6-luna` with high reasoning. Create one agent per failed task
instance, allow five minutes, and require the JSON result below.

```json
{
  "region": "us01",
  "client_id": "full UUID or null",
  "dag_id": "Airflow DAG ID",
  "run_id": "Airflow DAG run ID",
  "task_id": "Airflow task ID",
  "classification": "distinctness|timeout|confirmed_oom|probable_oom|unknown_resource_termination|application_error|unknown",
  "confidence": "confirmed|probable|unknown",
  "evidence_sources": ["oms"],
  "evidence": ["concise evidence"],
  "distinctness_checks": [
    {
      "dataset": "DatasetForm",
      "total": 0,
      "unique": 0,
      "status": "pass|mismatch"
    }
  ],
  "recoverable_opportunity_ids": [],
  "non_recoverable_opportunity_ids": [],
  "rerun_targets": [],
  "mutation_performed": false
}
```

The agent must not infer client identity, perform retries or resends, or broaden
its assigned task. If it times out, fails, or returns invalid JSON, run the
same deterministic parser locally and record `fallback: local_parser` in the
orchestrator's notes.

## Fast Airflow-log mode

Use this as the default for individual task parsing. Fetch the exact task
instance and attempt log through Airflow's authenticated UI session:

```bash
python3 .claude/skills/prod-support/scripts/get_airflow_task_logs.py \
  'https://airflow-<region>.precisionlender.com/dags/<dag-id>/grid' \
  --run-id '<run-id>' --task-id '<task-id>' --max-log-chars 0
```

When both run and task are supplied, the collector requests that exact task
instance instead of listing every task in the DAG run. Pass the captured text
to `investigate_oms_job.py --log-file` and then to the applicable domain
parser. The Luna agent receives only the captured log or its path and performs
local parsing without Azure authentication.

Use OMS fallback only when the Airflow log is unavailable or incomplete, the
required records exist only in OMS, EventBus payload volume makes the Airflow
response impractical, or the user explicitly requests an OMS comparison.

## OMS fallback mode

For OMS fallback, run the generic job-scoped classifier:

```bash
python3 .claude/skills/prod-support/scripts/investigate_oms_job.py \
  --region <region> --client-id <client-uuid> --dag-id <dag-id> \
  --task-id <task-id> --run-id <run-id> \
  --start-utc <start> --end-utc <end>
```

The query must filter by the exact client, task, and run. It searches OMS for
`OOMKilled`, `OutOfMemoryError`, out-of-memory text, SIGKILL/exit `-9`,
`**TimeoutError`, `ErrorTimeout`, `AirflowTaskTimeout`, `execution_timeout`,
and other explicit timeout text. Domain-specific parsers such as
`triage_high_quality.py` and `validate_event_bus_opportunities.py` run after
this generic classification.

Do not infer OOM or timeout from task duration alone. When OMS has no explicit
signal, return `unknown`; the orchestrator may separately cite Airflow metadata
as non-OMS evidence.

The orchestrator must keep source-specific conclusions separate:

- `OMS confirmed timeout`: OMS contains an explicit timeout marker.
- `Airflow confirmed timeout`: task metadata identifies an execution timeout,
  even if the job's OMS stream ends without a terminal message.
- `Unknown`: neither source contains sufficient evidence.

Do not rewrite `Airflow confirmed timeout` as an OMS finding. This distinction
is expected for tasks whose worker stops emitting OMS logs before Airflow
applies its execution timeout.

## OMS aggregation

Preserve attempt information during collection and deduplicate before
reporting.

High-quality records use this identity:

```text
client_id + run_id + task_id + dataset_form + total + unique
```

EventBus records use this identity:

```text
client_id + opportunity_id + recoverable
```

Apply these rules:

- Collapse identical records and report the attempts on which they appeared.
- Preserve conflicting records.
- Prefer the highest completed attempt for the final classification.
- Classify a dataset as a mismatch if the highest completed attempt reports a
  mismatch.
- If one opportunity is reported as both recoverable and non-recoverable,
  classify it as a conflict and exclude it from resend candidates.
