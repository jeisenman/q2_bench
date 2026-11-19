# Failure classifications

## Resource termination and OOM

Use the narrowest supported classification:

| Classification | Required evidence |
| --- | --- |
| `confirmed_oom` | `OOMKilled`, Kubernetes reason `OOM`, or explicit `OutOfMemoryError` |
| `probable_oom` | SIGKILL or exit `-9` plus memory-pressure evidence and no conflicting cause |
| `unknown_resource_termination` | SIGKILL or exit `-9` without corroborating evidence |
| `not_oom` | A different explicit terminal cause |

For probable or unknown cases, do not report plain `OOM`. State the evidence
that supports the confidence level.

## Timeout evidence

Use source-qualified timeout classifications:

| Classification | Required evidence |
| --- | --- |
| `oms_confirmed_timeout` | `**TimeoutError`, `ErrorTimeout`, `AirflowTaskTimeout`, `execution_timeout`, or explicit timeout text in the exact job's OMS stream |
| `airflow_confirmed_timeout` | Airflow task-instance metadata identifies execution timeout or records duration exceeding the configured execution timeout |
| `unknown` | Neither source contains an explicit timeout signal |

An OMS stream that ends without a terminal error does not prove a timeout.
When sources differ, report both `OMS: unknown` and
`Airflow: confirmed timeout`.

## Delivery-to-Promise and subscriber failures

For the same task and each affected client, query the prior 30 days. Assign
one status:

- `new`: no matching prior failure.
- `known_recurring_unchanged`: affected clients and root cause are unchanged.
- `known_recurring_changed`: client set, failure rate, success pattern, or root
  cause changed.
- `recovered`: the current operational run succeeded after prior failures.

Include `new` and `known_recurring_changed` findings in the primary report.
Put `known_recurring_unchanged` only in the developer message under `Known
recurring`. Omit it from the Data Internal Channel message unless it has a new
OOM, distinctness, timeout, or production-impact signal.

## Airflow failure to OMS classification

Use these steps when an Airflow failure needs `DI_Scheduling_CL` evidence:

1. Parse the exact Airflow attempt. Record the region, full client UUID,
   DAG ID, task ID, run ID, attempt number, and operational `window_start_t`.
2. Use the exact Airflow log for root cause and details. Do not query OMS
   for information already in that log.
3. Choose the narrowest query for the failure class. Keep available client,
   task, run, job-status, and target-window filters.
4. For the EventBus opportunity summary, omit `try_number_d` unless you
   need one attempt. Omitting it is more reliable for this query.
5. Match the OMS production workspace to the Airflow region: `pl-oms-us-primary`
   for US-01 and `pl-oms-ca-primary` for CA-02.
6. Use Kusto UTC literals like `datetime('YYYY-MM-DDT05:00Z')`. For a full
   day, use `startofday(window_start_t)` and a bounded `TimeGenerated` range.

### Recoverable v2 EventBus opportunity snapshots

Use this for `validate_event_bus_opportunities` failures when the Airflow log
does not contain a manageable payload. It identifies recoverable opportunity
IDs grouped by client and intentionally does not filter by attempt:

```kusto
DI_Scheduling_CL
// target date
| where window_start_t == datetime('2023-09-05T05:00Z')
| where task_id_s == 'validate_event_bus_opportunities'
| where job_status_s == 'VAL3002'
| extend OppId = extract("OpportunityId: ([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", 1, Message)
| extend IsRecoverable = extract("Is Recoverable: (True|False)", 1, Message)
| where IsRecoverable == 'True'
| summarize OppIds = make_set(OppId) by client_id_g
| extend FormattedOppIds = strcat_array(OppIds, ", ")
| extend QtyOppIds = array_length(OppIds)
| project client_id_g, FormattedOppIds, QtyOppIds
| order by client_id_g asc
```

For a rolling prior-day query, replace the exact target-window line with:

```kusto
| where startofday(window_start_t) == startofday(ago(1d))
```

Use the result only to prepare client-scoped resend candidates. Deduplicate
IDs, keep recoverable and non-recoverable IDs separate, and resolve each
client's environment through Resource Discovery before proposing a resend.

### Generic unhandled-error triage

Use this for the daily production-support error inventory. It excludes
backfills and known non-actionable validation statuses:

```kusto
let the_date = startofday(ago(1d));
DI_Scheduling_CL
| where TimeGenerated >= ago(2d)
| where startofday(window_start_t) == the_date
| where backfill_flag_d == false
| where log_level_s in ('CRITICAL', 'ERROR')
    or job_status_s !in ('', 'VAL1001', 'VAL2001', 'VAL2002', 'VAL3001', 'VAL3004')
| order by log_level_s asc, job_status_s asc
| limit 1000
| project data_factory_name_s, pipeline_name_s, activity_name_s, log_created_s, log_level_s, Message
```

### Pipeline and activity classification

Use these progressively narrower queries:

```kusto
// Activity
DI_Scheduling_CL
| where activity_name_s == "PortfolioMarketReport"
| where TimeGenerated between (startofday(ago(1d)) .. now())

// Pipeline
DI_Scheduling_CL
| where pipeline_name_s == "MarketInsightsReport"
| where TimeGenerated between (startofday(ago(1d)) .. now())

// Error level
DI_Scheduling_CL
| where log_level_s in ('ERROR', 'CRITICAL')
| project TimeGenerated, client_id_g, activity_name_s, Message

// Activity status
DI_Scheduling_CL
| where activity_name_s == "PortfolioMarketReport"
| where job_status_s == "VAL1001"
| where TimeGenerated between (startofday(ago(1d)) .. now())
| project client_id_g, job_status_s, Message
```

### Other recurring classifications

```kusto
// Dry-run deletion logs
let jira = "QDS4869";
DI_Scheduling_CL
| where pipeline_name_s == strcat("delete_hard_coded_paths_dag", jira)
| where Message startswith "DRY RUN: deleted path:"
| project TimeGenerated, client_id_g, pipeline_name_s, task_id_s, Message
| order by client_id_g asc, TimeGenerated desc

// Ignored RA columns
DI_Scheduling_CL
| where window_start_t >= ago(7d)
| where task_id_s startswith "ra_group"
| where Message contains "is missing from INFILE_DTYPES"
| extend MissingColumn = extract(
    'field "([A-z0-9_].*)" in csv is missing from INFILE_DTYPES... ignoring this field',
    1,
    Message
  )
| distinct ra_file_s, task_id_s, MissingColumn
| order by ra_file_s, MissingColumn
```

An OMS query with no matching rows does not disprove the Airflow failure.
Report the failure and label the OMS result `no matching OMS evidence`.
