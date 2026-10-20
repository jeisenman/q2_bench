# KPO timeout sizing

Use the read-only Databricks notebook when a failed task has explicit timeout
evidence and the task appears in the KPO inventory:

```text
/Shared/Data Pipelines/Prod Support/KPO ADLS Size Inventory
```

Add this exact follow-up before running it:

```text
Would you like to inspect the job's ADLS input size and compare it with jobs using the same KPO runner size?
```

If the user agrees, report the failed job/client's measured input size,
configured KPO CPU and memory, and same-tier peers.

The notebook inventories explicit per-client `container_resources` overrides
from `dag-utils/resource_allocation.py`. It measures the latest source RA file
or Historical Data Mart date partition, sorts results by KPO memory and input
size, and summarizes jobs sharing the same memory tier. The
`relationship_signals_time_series_agg_cp_to_snowflake` job measures its complete
`VersionPartition` root regardless of the `latest_only` setting.

Inventory rows use client UUIDs only. Resolve client names through Resource
Discovery; comments beside overrides are historical notes and are not an
authoritative identity source.

Run it on an existing approved Data Engineering production cluster. Set
`client_ids` to the failed client UUID whenever possible. The default storage
account is `pladls2usdatamartprod`; use `storage_account_overrides_json` for
clients on dedicated accounts. Treat `unavailable` rows as missing access or
path evidence, not as zero-byte inputs.

The checked-in notebook source is
`assets/kpo_adls_size_inventory.py`. Refresh it after KPO override or source
dataset changes:

```bash
python3 {{SKILL_DIR}}/scripts/build_kpo_size_notebook.py \
  --di-pipelines-root <di-pipelines-root> \
  --source-commit <di-pipelines-commit> \
  --output {{SKILL_DIR}}/assets/kpo_adls_size_inventory.py
```

Review the generated notebook before importing it. Importing or replacing a
workspace notebook is an external write; require the user's authorization when
the current request has not already requested deployment.

Do not recommend a KPO size from file size alone. Compare the failed
job/client with measured peers on the same job and memory tier, then account
for file format, row width, parsing behavior, concurrency, and whether the
failure was actually a timeout rather than OOM.

## Live memory profiling

Use the live profile only for an exact failed `SparkSubmitOperator` or
`KubernetesPodOperator` task:

1. Call `prepare_kpo_memory_profile` with the complete region, DAG ID, run ID,
   and task ID. It must pass the regional Kubernetes metrics preflight before
   offering a retry candidate.
2. Present the returned retry candidate and obtain explicit user approval.
3. Call `execute_prod_support_follow_up` with the preserved candidate,
   validation URLs, direction, correlation ID, and approval reference.
4. Call `watch_kpo_task_memory` with the returned watch input. Pass its
   complete `history` into each later watch call until `complete` is true or
   the user stops monitoring.

Do not call the watcher against the baseline failed attempt. It requires an
Airflow try number newer than `baseline_try_number`.

One watcher call is bounded to five minutes. It maps the new Airflow attempt's
log to the exact Kubernetes pod. For Spark it follows `spark-app-selector` and
records the driver and all currently visible executors. It returns exact byte
usage, pod limits, utilization, explicit `OOMKilled` evidence, graph-ready
points, and a compact graph preview.

The MCP process must have the regional `kubectl` context and access to the
Kubernetes Metrics API. Missing metrics are evidence gaps. `oom_observed=false`
means no OOM was present in retained samples; it does not prove that an
unsampled or already-deleted pod never OOMed.
