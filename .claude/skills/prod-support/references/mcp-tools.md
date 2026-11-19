# MCP composition

This skill combines typed connector calls. The current agent controls their
order, compares evidence, classifies failures, and writes the report. Delegate
Chrome checks and authorized manual recovery to GPT-6.1 Terra.

## Connector ownership

| MCP server | Tools used by this skill | Purpose |
| --- | --- | --- |
| `prod-support` | `inspect_cluster_health`, `get_prod_support_omissions`, `list_failed_task_instances`, `get_dag_status`, `get_task_instance_state`, `get_task_log`, `has_task_success`, `get_task_metadata` | Cluster and DAG guards, settings, discovery, exact state, and Airflow evidence |
| `remote-data` | `query_job_evidence`, `query_oms` | Bounded production OMS fallback |
| `prod-support` | `execute_prod_support_follow_up` | Approval-gated exact failed-task retries and backward-compatible changed-dataset re-runs |
| `prod-support` | `plan_prod_support_dependency_rerun`, `execute_prod_support_dependency_rerun` | Approval-gated recomputation of non-failed downstream tasks in explicitly listed DAG runs |
| `prod-support` | `get_kpo_job_templates`, `estimate_kpo_resources` | Conditional, read-only KPO sizing |
| `prod-support` | `prepare_kpo_memory_profile`, `watch_kpo_task_memory` | Exact retry preparation and read-only pod/process memory profiling |

The standalone `airflow` server has the same five Airflow read tools. The
standalone `oms` server has `query_oms`. Prefer tools from the named skill
dependencies. Do not repeat a query across servers.

## Cluster-health contract

Call once per selected region. Pass the bounded operational day:

```json
{
  "region": "US-01",
  "start_at": "2026-10-13T05:00:00Z",
  "end_at": "2026-10-14T05:00:00Z"
}
```

The result reports cluster existence, pod readiness, restart counts, active
DAG count, and DAG-parsing health separately. An unavailable or partial result
is not healthy.

## Airflow contracts

Pass an RFC3339 cutoff to discovery:

```json
{
  "since": "2026-10-13T05:00:00Z"
}
```

Pass `region: "US-01"` or `region: "CA-02"` only for an explicit regional
scope. If you omit region, the tool returns both.

After discovery, check every unique DAG identity:

```json
{
  "region": "US-01",
  "dag_id": "l3-main-<client-uuid>"
}
```

If `exists: false` or `is_paused: true`, do not collect task evidence or
select a retry for that DAG. Keep the discovered failure in the report.

Pass a returned failure unchanged to exact-task tools:

```json
{
  "failure": {
    "region": "US-01",
    "dag_id": "l3-main-<client-uuid>",
    "run_id": "<exact-run-id>",
    "task_id": "<exact-task-id>",
    "start_at": "<RFC3339 timestamp>",
    "end_at": "<RFC3339 timestamp>",
    "try_number": 1
  }
}
```

Pass `start_at` and `end_at` to `has_task_success` for its bounded comparison
window. `get_task_metadata` returns the exact operator name. Use it only to
check whether a Spark-backed OMS stream is plausible.

## OMS contracts

For one Spark-backed task attempt, prefer `query_job_evidence`:

```json
{
  "parameters": {
    "region": "us",
    "client_id_g": "<complete-client-uuid>",
    "run_id_s": "<exact-run-id>",
    "task_id_s": "<exact-task-id>",
    "try_number_d": 1,
    "start_at": "2026-10-13T05:00:00Z",
    "table": "DI_Scheduling_CL"
  }
}
```

Map `US-01` to `us` and `CA-02` to `ca`. Use `query_oms` only for a bounded
domain query across attempts or when the exact-job contract cannot represent
the query:

```json
{
  "environment": "production",
  "region": "us",
  "kql": "<narrow allowlisted KQL ending with a row limit>",
  "timespan": "<explicit bounded timespan>"
}
```

Keep every available client, run, task, window, and attempt filter. EventBus
aggregation is the only routine query that may omit the attempt filter.

## Availability and failure behavior

- If Airflow MCP fails or is absent, have GPT-6.1 Terra verify the Chrome
  connection before reporting a blocker. Use visible UI evidence under the
  [browser fallback](browser-verification.md#airflow-mcp-fallback), then perform
  authorized manual resends/retries under [eventbus-recovery.md](eventbus-recovery.md)
  and [retries.md](retries.md). Missing MCP alone is not a recovery blocker.
- Do not substitute shell scripts, browser scraping, direct HTTP calls, or
  Azure CLI queries for missing evidence.
- Keep facts returned by available connectors.
- Mark only unsupported evidence or remediation as unavailable.
- An unavailable log or empty OMS result does not mean the task succeeded.
- Do not call mutation tools while completing the read-only report. The
  `kubectl`-backed cluster check is optional for the later approved Airflow
  follow-up; the follow-up still requires exact candidates and Airflow DAG
  guards.

## Retained compatibility façade

Keep `run_prod_support` for explicit compatibility and benchmark use. It is
not the default live route. Do not merge its report with a connector-driven
run. If used, present its warnings and source as returned.

Omission setters change future reporting policy. Confirm intent before
calling `set_prod_support_omissions` or `update_prod_support_omissions`. Never
change omissions during daily support.

## KPO memory-profile contracts

Call `prepare_kpo_memory_profile` with the exact failed-task identity. It
checks the DAG, failure state, operator, and current try number. It returns the
candidate and baseline for the approval-gated retry.

After the approved retry, call `watch_kpo_task_memory` with the preserved
baseline. It will not sample the old attempt. Each call lasts at most five
minutes. Pass its returned `history` to the next call. Spark profiles follow
the driver pod's `spark-app-selector` and include executors. The watcher reads
`kubectl` and `metrics.k8s.io`. Batch profiles also inspect processes through
read-only `pods/exec`; preparation requires that permission. `BashOperator`
history includes `batch_process` with root PID, process count, RSS bytes, and
availability. Treat worker pod metrics and OOM evidence as shared context;
do not attribute them only to the profiled task. See
[kpo-sizing.md](kpo-sizing.md#batch-tasks-on-shared-airflow-workers).
