# MCP composition

Interactive production support is a Markdown-orchestrated composition of typed
connector calls. The current agent owns ordering, evidence comparison,
classification, and reporting. It does not delegate failures to subagents.

## Connector ownership

| MCP server | Tools used by this skill | Purpose |
| --- | --- | --- |
| `prod-support` | `inspect_cluster_health`, `get_prod_support_omissions`, `list_failed_task_instances`, `get_dag_status`, `get_task_instance_state`, `get_task_log`, `has_task_success`, `get_task_metadata` | Cluster and DAG guards, settings, discovery, exact state, and Airflow evidence |
| `remote-data` | `query_job_evidence`, `query_oms` | Bounded production OMS fallback |
| `prod-support` | `execute_prod_support_follow_up` | Approval-gated exact Airflow retry execution |
| `prod-support` | `get_kpo_job_templates`, `estimate_kpo_resources` | Conditional, read-only KPO sizing |

The standalone `airflow` server exposes the same five Airflow read tools, and
the standalone `oms` server exposes `query_oms`. Prefer the tools already
available through the named skill dependencies; do not duplicate the same
query across servers.

## Cluster-health contract

Call once per selected region with the bounded operational day:

```json
{
  "region": "US-01",
  "start_at": "2026-10-13T05:00:00Z",
  "end_at": "2026-10-14T05:00:00Z"
}
```

The result separately reports cluster existence, pod readiness, restart
counts, active DAG count, and DAG-parsing health. Do not promote an unavailable
or partial response to healthy.

## Airflow contracts

Call discovery with an RFC3339 cutoff:

```json
{
  "since": "2026-10-13T05:00:00Z"
}
```

Use optional `region: "US-01"` or `region: "CA-02"` only for explicit
regional scope. An omitted region returns both.

After discovery, check every unique DAG identity:

```json
{
  "region": "US-01",
  "dag_id": "l3-main-<client-uuid>"
}
```

`exists: false` or `is_paused: true` blocks task evidence collection and retry
selection for that DAG, but does not remove the discovered failure from the
report.

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

`has_task_success` also requires `start_at` and `end_at` for the bounded
comparison window. `get_task_metadata` returns the exact operator name; use it
only to decide whether a Spark-backed OMS stream is plausible.

## OMS contracts

Prefer `query_job_evidence` for one Spark-backed task attempt:

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

Map `US-01` to `us` and `CA-02` to `ca`. Use `query_oms` only when a bounded
domain query must span attempts or cannot be represented by the exact-job
contract:

```json
{
  "environment": "production",
  "region": "us",
  "kql": "<narrow allowlisted KQL ending with a row limit>",
  "timespan": "<explicit bounded timespan>"
}
```

Keep all available client, run, task, window, and attempt filters. EventBus
aggregation is the only routine case that may intentionally omit the attempt
filter.

## Availability and failure behavior

- Do not replace a missing MCP tool with a shell script, browser scrape, direct
  HTTP call, or Azure CLI query.
- Preserve facts already returned by available connectors.
- Mark only the unsupported evidence or remediation as unavailable.
- Do not classify an unavailable log or empty OMS result as a successful task.
- Do not call mutation tools while completing the read-only report. The
  `kubectl`-backed cluster check is optional for the later approved Airflow
  follow-up; the follow-up still requires exact candidates and Airflow DAG
  guards.

## Retained compatibility façade

`run_prod_support` remains available for explicit compatibility and benchmark
use. It is not the default live route and its report must not be
merged with a connector-driven run. When it is explicitly used, present its
returned warnings and source without rewriting them.

Omission setters change future reporting policy. Confirm intent before calling
`set_prod_support_omissions` or `update_prod_support_omissions`; never change
omissions as a side effect of daily support.
