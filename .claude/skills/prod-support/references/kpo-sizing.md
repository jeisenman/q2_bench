# KPO sizing and memory trends

For a requested comparison across dates, input growth investigation, or graph
of memory usage/allocation, read [kpo-memory-trends.md](kpo-memory-trends.md).
It combines exact input metadata with captured memory samples and produces
separate data-size and memory charts. It also covers Spark tasks whose
historical inputs differ from their upstream KPO source files.

Use the read-only Databricks notebook when a failed task has explicit timeout
evidence and the task appears in the KPO inventory:

```text
/Shared/Data Pipelines/Prod Support/KPO ADLS Size Inventory
```

When offering an unsolicited sizing investigation, use this follow-up:

```text
Would you like to inspect the job's ADLS input size and compare it with jobs using the same KPO runner size?
```

When the user requests or accepts the investigation, report its measured input size,
configured KPO CPU and memory, and same-tier peers.

The notebook inventories explicit per-client `container_resources` overrides
from `dag-utils/resource_allocation.py`. It measures the latest source RA file
or Historical Data Mart date partition, sorts results by KPO memory and input
size, and summarizes jobs sharing the same memory tier. The
`relationship_signals_time_series_agg_cp_to_snowflake` job measures its complete
`VersionPartition` root regardless of the `latest_only` setting.

Inventory rows use client UUIDs only. Resolve client names through Resource
Discovery. Comments beside overrides are historical notes. Do not use them
as an authoritative identity source.

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

Review the generated notebook before you import it. Importing or replacing a
workspace notebook is an external write. Require the user's authorization
unless the current request already requested deployment.

Do not recommend a KPO size from file size alone. Compare the failed
job/client with measured peers on the same job and memory tier, then account
for file format, row width, parsing behavior, concurrency, and whether the
failure was a timeout or OOM.

## Live memory profiling

Use the live profile for an exact failed `SparkSubmitOperator`,
`KubernetesPodOperator`, or batch `BashOperator` task:

1. Call `prepare_kpo_memory_profile` with the complete region, DAG ID, run ID,
   and task ID. It must pass the regional Kubernetes metrics preflight before
   offering a retry candidate.
2. Present the exact retry candidate. Reuse an existing explicit request to run
   and watch that same task/run; otherwise obtain approval before retrying.
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
means no OOM was present in retained samples. It does not prove that an
unsampled or already-deleted pod never OOMed.


### Batch tasks on shared Airflow workers

Keep the deployed batch runner when you investigate worker pressure or
cleanup. A dedicated-pod change measures a different execution environment.
The same prepare/retry/watch tools support `BashOperator`. Preparation requires
Metrics API access and `pods/exec` permission for bounded read-only process
inspection. It never triggers the task itself.

The watcher reads the exact new attempt log to identify its worker hostname
and task-runner PID. It verifies DAG, run, and task arguments inside the worker,
checks process start ticks against PID reuse, and sums RSS for that root and
its descendants. Commands return only numeric process statistics. Do not
collect command lines, environment variables, credentials, or job payloads.
Missing or ambiguous identity is unavailable evidence, never a zero-byte job.

Report `batch_process.rss_bytes` and `peak_batch_process_rss_bytes` separately
from worker pod memory, limit, utilization, and OOM status. The graph labels
these as `task_process_tree_rss` and `shared_worker_memory`. RSS counts shared
pages per process and can overcount physical memory. Worker metrics include
other concurrent tasks. A worker OOM does not identify which task caused it.
When the task process has exited, retain the last observations and mark process
usage unavailable. Do not infer a leak from worker usage or claim a true peak
between samples. No `gc.collect()` or runner-size change is justified solely
by sustained worker memory. Compare repeated runs under the same runner and
record process exit plus concurrent worker activity before diagnosing cleanup.
