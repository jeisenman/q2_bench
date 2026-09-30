# OMS and Airflow task translation

Use OMS for raw, bounded Log Analytics evidence when the exact Airflow task log
is unavailable, incomplete, too large, or the user explicitly requests an OMS
comparison. Production-support classification remains outside the
`remote_data` skill.

## Airflow identity maps directly to OMS

`di-pipelines/dag-utils/operators.py` establishes the identity contract:

| Airflow value | `DI_Scheduling_CL` field |
| --- | --- |
| task instance `task_id` | `task_id_s` |
| DAG run `run_id` | `run_id_s` |
| task attempt | `try_number_d` |
| DAG `dag_id` | `pipeline_name_s` |
| task client parameter | `client_id_g` |
| data interval start | `window_start_t` |

The operator builder uses `job_name` as the Airflow `task_id`, then injects
Airflow's rendered task ID into the job activity. Therefore:

- use the exact task instance ID returned by Airflow;
- retain TaskGroup prefixes such as `ra_group.` or
  `delivery_to_promise.`;
- do not strip a client suffix from a generated task ID;
- do not substitute the Python class, module, display label, or
  `activity_name_s` for `task_id_s`.

## Choose the OMS workspace

| Airflow region | MCP region | Workspace |
| --- | --- | --- |
| `US-01` | `us` | `pl-oms-us-primary` |
| `CA-02` | `ca` | `pl-oms-ca-primary` |

Only use `environment: production` for these production Airflow regions.
Before direct Log Analytics work, verify the active Azure subscription is
`71aa0ec0-8411-43a2-9908-ddd2add764eb`.

## Preferred exact-job query

For a client-scoped Spark task, call `query_job_evidence`:

```json
{
  "parameters": {
    "region": "us",
    "client_id_g": "<complete-client-uuid>",
    "run_id_s": "<exact-airflow-dag-run-id>",
    "task_id_s": "<exact-airflow-task-id>",
    "try_number_d": 1,
    "start_at": "2026-09-28T05:00:00Z",
    "table": "DI_Scheduling_CL"
  }
}
```

`start_at` must include a timezone. The tool derives the operational window as
05:00 UTC on that date through 05:00 UTC the next day and projects the raw
timestamp, message, level, and pod fields in chronological order.

Use the complete client UUID. A three-character client code is report
formatting only and is never a valid OMS filter.

## When exact-job parameters are unavailable

First read Airflow task metadata. OMS routing is supported for Spark-backed
jobs. Branch, trigger, short-circuit, and other Airflow-control operators may
not emit a corresponding `DI_Scheduling_CL` stream; use their exact Airflow
task log instead of fabricating an OMS query.

For a Spark task without a client identity, or for a domain-specific summary
that intentionally spans attempts, call `query_oms` with narrow KQL and an
explicit timespan:

```kusto
DI_Scheduling_CL
| where window_start_t == datetime('2026-09-28T05:00Z')
| where run_id_s == '<exact-airflow-dag-run-id>'
| where task_id_s == '<exact-airflow-task-id>'
| project TimeGenerated, client_id_g, run_id_s, task_id_s,
    try_number_d, job_status_s, message_s
| order by TimeGenerated asc
| limit 1000
```

Add `client_id_g` and `try_number_d` filters whenever they are known. Do not
drop exact identity filters merely to obtain rows.

## Domain-specific exceptions

- EventBus opportunity summaries may intentionally span attempts; omit
  `try_number_d` only for that explicit aggregation.
- For pipeline or activity investigations, derive `pipeline_name_s` from the
  DAG ID and `activity_name_s` from the job's activity arguments in
  `<repositories.root>/di-pipelines`. Do not guess either value.
- A successful query with zero rows means `no matching OMS evidence`; it does
  not disprove the Airflow failure.
- Keep OMS and Airflow conclusions source-qualified. An Airflow execution
  timeout is not an OMS timeout unless OMS contains an explicit timeout
  marker.

Use the production-support reference
[`classifications.md`](../../prod-support/references/classifications.md) when
the raw evidence must be
classified as OOM, timeout, EventBus validation, or another supported failure
type.
