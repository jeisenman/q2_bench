# Direct investigation contracts

Investigate each exact failure identity. Connector calls may run in parallel
to reduce latency, but keep evidence separate by region, DAG, run, task, and
attempt.

## Evidence record

Maintain one record per failed task instance with:

```text
region
client_id or unresolved
dag_id
run_id
task_id
try_number
classification and confidence
evidence sources
concise evidence
distinctness checks
recoverable and non-recoverable opportunity IDs
rerun targets
mutation_performed=false
```

Never merge evidence from different run IDs or task attempts merely because
their task IDs match.

## Exact Airflow log first

Call `get_task_log` before querying OMS. Review the complete log for:

- explicit application exceptions and terminal causes;
- `OOMKilled`, Kubernetes OOM reason, or `OutOfMemoryError`;
- SIGKILL and exit `-9`;
- `**TimeoutError`, `ErrorTimeout`, `AirflowTaskTimeout`,
  `execution_timeout`, and other explicit timeout text;
- distinctness counts and explicit distinctness exceptions;
- ordered EventBus `ClientId`, `OpportunityId`, and `Is Recoverable` records.

Do not infer OOM or timeout from duration alone. Use the captured markers
and [classifications.md](classifications.md).

## OMS fallback

Use OMS only if the exact Airflow log is unavailable or incomplete, is too
large for the required EventBus aggregation, or the user requests a comparison.

If needed, call `get_task_metadata` before `query_job_evidence`. Branch,
trigger, short-circuit, and other Airflow-control operators may not emit a
`DI_Scheduling_CL` stream.

For an exact-job query, keep these filters:

```text
client_id_g + run_id_s + task_id_s + try_number_d + operational window
```

Use `query_oms` only for bounded aggregation across attempts. Set an explicit
timespan and a row limit of 1,000 or less. Label a zero-row response `no
matching OMS evidence`.

Report source conclusions separately:

- `OMS confirmed timeout` requires an explicit OMS timeout marker.
- `Airflow confirmed timeout` requires exact Airflow log or metadata evidence.
- `Unknown` means neither source supports a terminal cause.

## EventBus aggregation

Treat each ordered triple as one record:

```text
ClientId: <uuid>
OpportunityId: <uuid>
Is Recoverable: True|False
```

Deduplicate on:

```text
client_id + opportunity_id + recoverable
```

Preserve the attempts on which a record appeared. If the same client and
opportunity occur with both recoverability values, report a conflict and
exclude it from resend candidates. Keep non-recoverable IDs separate.

When Airflow evidence is incomplete, a bounded `query_oms` aggregation may
span attempts for the same operational window and task. Do not broaden the
query to unrelated tasks or dates.

## High-quality distinctness

Capture every `Validate distinctness - counts` record, including passing
records. Normalize each as:

```text
dataset form + total + unique + pass|mismatch
```

Deduplicate on:

```text
client_id + run_id + task_id + dataset form + total + unique
```

Prefer the highest completed attempt for the final status while preserving
conflicting prior evidence. A mismatch exists when total and unique differ or
the exact evidence explicitly names a distinctness validation failure.

Generate only proven underlying `ra_group.get_*` targets. Never map a passing
dataset because another dataset in the same task failed. A timeout-only or
OOM-only high-quality failure has no distinctness rerun target.

A distinctness failure can result from the upstream job writing data twice,
even when that job reports success. For the proven mismatched dataset, plan
to rerun its exact upstream producer regardless of its current success state,
then validate the output and rerun affected downstream tasks. Use the guarded
dependency-rerun procedure in [retries.md](retries.md); do not treat success
as proof that the output is distinct or bypass its execution guards.

## D2P and subscriber history

For a D2P or subscriber failure, retrieve one additional 30-day failure
inventory. Filter it locally by exact task and affected client. Use bounded
success checks when needed. Compare:

- affected client set;
- prior failure presence;
- intervening success;
- root-cause class;
- new OOM, timeout, distinctness, or production-impact signals.

Use a status from [classifications.md](classifications.md). Do not query OMS
only to confirm an omission or recurrence.

## Unsupported and other failures

For an unrecognized `l3-main-*` task, report its exact Airflow identity and
narrowest supported terminal cause under `Other`. Keep it in the report even
if a secondary source is unavailable.
