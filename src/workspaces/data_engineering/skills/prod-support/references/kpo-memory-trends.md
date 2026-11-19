# Memory and input growth over time

Use this workflow for dated KPO/Spark memory graphs and comparisons with an
earlier run or resource increase. A size-comparison request already authorizes
the read-only measurements. It does not authorize rerunning an Airflow task.

## Collect comparable evidence

1. Resolve the exact client, region, task, DAG run, attempt, start/end time,
   and operator using Airflow. For “today,” state both the failure date and
   logical run date. They can differ. Read the exact attempt log first.
2. Trace the task's job reference, input resource, path convention, format,
   versions, date selection, and source filenames. A downstream high-quality
   Spark task can read complete historical Primary and Derived datasets
   even when the upstream RA ingestion tasks are skipped. Measure the scope
   the failed task actually reads.
3. Resolve dedicated storage accounts from the log or effective Contx
   metadata. Do not assume the shared production account. Use approved
   read-only remote-data capabilities or authenticated ADLS metadata APIs.
   Do not read complete CSV/parquet contents merely to measure bytes.
4. Record exact paths, byte counts, file counts, versions, source/partition
   dates, measurement time, and last-modified timestamps. Include both
   changed and `Unchanged` source CSVs when the runner reads both. Expand
   wildcard versions/dates explicitly. Never substitute the latest partition
   for the task's complete historical input without telling the user.
5. For an earlier date, select the actual earlier run/input, or identify the
   latest source available on or before that date. State its actual data
   date. A `DatePartition=20260612` folder is not a June 15 snapshot: it may
   have been rewritten later. Label retained partitions and cumulative
   partition-date reconstructions accordingly. Original source files whose
   last-modified timestamps precede the comparison are stronger baseline
   evidence. Missing historical logs/files remain unavailable, never zero.
6. Obtain memory requests and limits from the exact attempt's rendered pod
   or logs. Repository/Git settings can establish configuration history.
   Preserve their commit and label them `repository_configuration`. A commit
   date does not prove a production deployment date. For Spark,
   keep driver heap, executor heap, actual pod limits including overhead,
   and application totals distinct.
7. Use retained Kubernetes/monitoring samples for observed usage. The
   existing `watch_kpo_task_memory` response can be attached directly to
   an observation. For a new approved retry, follow the live profiling
   procedure in [kpo-sizing.md](kpo-sizing.md). Do not retry solely to fill a
   chart without the retry authorization required there.

Use one immutable observation per client/task/run/attempt/comparison date and
memory/input scope. Preserve raw watcher history and metadata evidence as
local artifacts, then append observations for future comparisons. Do not
overwrite an earlier captured measurement by listing its paths again today.
No scheduled collection or external persistence is implied by this workflow.

## Repeatable chart notebook

`assets/kpo_memory_trends.py` accepts an `observations_json` widget containing
a JSON array. It plots input GiB and memory GiB in separate aligned panels,
returns the normalized observations and percentage changes as JSON, and
performs no remote writes. The same SOURCE can be executed with a local
Databricks runtime adapter for offline graphs of already captured evidence.
Review it before remote execution. Use an approved existing cluster.

Record shape (use measured byte values; the null fields below are unknown):

```json
{
  "client_id": "<full UUID>",
  "region": "US-01",
  "dag_id": "l3-main-<full UUID>",
  "task_id": "ra_group.get_loan_financial_statement_breakdown",
  "run_id": "<exact Airflow run ID>",
  "try_number": 1,
  "comparison_at": "2026-06-15T23:59:59Z",
  "data_date": "2026-06-12",
  "input_scope": "ra_source_csv",
  "input_bytes": null,
  "input_paths": ["abfss://<filesystem>@<account>.dfs.core.windows.net/<exact-file>"],
  "data_basis": "original_source",
  "memory_scope": "pod",
  "memory_request_bytes": null,
  "memory_limit_bytes": null,
  "allocation_basis": "runtime_pod",
  "peak_memory_bytes": null,
  "memory_sample_count": 0,
  "memory_evidence": null,
  "measured_at": "<UTC timestamp>",
  "evidence": ["<Airflow/log/metadata artifact reference>"]
}
```

For captured input data, supply `input_bytes` and preserve its original
metadata. When `input_bytes` is null and explicit `input_paths` are supplied,
the notebook lists metadata recursively with a configurable `max_files`
bound, deduplicates overlapping paths, and records each file and timestamp.
It labels these measurements `retained_files_measured_now` and flags any
file modified after `comparison_at`. It cannot reconstruct deleted files.
Stop the run on an access/listing error. Do not produce an incomplete sum.

For observed memory, attach the full exact watcher result as
`memory_profile`. The notebook validates region/DAG/run/task identity,
filters samples to `try_number`, and computes peaks only from samples with
metrics for every selected pod. Supported scopes are `pod`, `driver`,
`max_executor`, and `application_total`. Alternatively supply measured
`peak_memory_bytes`, a positive `memory_sample_count`, and
`memory_evidence` from retained monitoring. Use separate observations for
different scopes. Missing metrics remain null even if a watcher summary has
numeric zero defaults.

Keep `input_scope` and `allocation_basis` consistent within each comparison:
the notebook groups by client, task, input scope, memory scope, and allocation
basis. Use descriptive input scopes when formats or measurement scopes
differ. An application-total limit changes as executors scale. Do not
compare it with one executor's limit or a sum of per-pod lifetime peaks.

## Deliver the result

Return the graph, observation JSON, baseline/current byte values and growth
percentages, actual data dates, configured request/limit, sampled peak and
sample coverage when known, plus evidence gaps. Graph unknown values as
gaps. Never replace them with zero or infer RAM usage from input bytes.
An observed sampled maximum is a lower bound on lifetime peak usage.
Annotate changes in runner, schema/row width, compression, chunk size, or
concurrency that weaken a comparison.

Classify the actual failure separately. A storage-listing timeout alone does
not establish memory pressure or justify increasing RAM. File growth,
configured memory growth, and observed memory growth are three different
measurements.
