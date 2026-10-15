# KPO sizing estimator

The `prod-support` MCP server exposes two deterministic, read-only wrappers
around the pure Go `kposizing` package:

- `get_kpo_job_templates` lists the bounded verified job catalog or resolves a
  canonical job name or documented alias.
- `estimate_kpo_resources` estimates a workload directly or applies one
  verified job template before estimation.

Neither tool performs network calls, reads production systems, or changes
allocations.

## Planning boundary

This is a static planning estimate, not calibrated production truth. It models
the peak working set for one explicitly selected transformation family using
the supplied pre-run evidence:

```text
peak bytes = sum of family-specific components
headroom bytes = peak bytes × configured headroom, rounded upward
requested bytes = peak bytes + headroom bytes
recommended tier = smallest configured tier at least as large as requested bytes
```

Configured historical tiers are rounding targets, not labels or claims that a
job belongs to a tier. A request above the largest tier is rejected instead of
being rounded down.

Without a job template, the caller must provide the exact job, runner, family,
and all resolved inputs required by the selected family. With a job template,
the catalog can supply canonical job identity, a verified runner/family route,
and known static chunk or concurrency values. Supplied values must agree with
the template.

Templates never manufacture measured runtime-dependent evidence. File sizes,
row widths, expanded or encoded bytes, Spark partition working-set inputs, CPU,
and other family-required observations remain mandatory. Missing or
contradictory evidence causes the tool to abstain with an actionable error.

A timeout is duration evidence, not out-of-memory evidence. Do not use a timeout
alone to increase memory or infer a working-set component.

## Input and configuration

The estimate input contains one typed `kposizing.Workload` and an optional
`job_template`:

- direct mode requires `job`, exact `runner`, and transformation `family`;
- template mode may omit those identity fields and known static chunk or
  concurrency fields;
- current CPU millicores and measured family-specific profile evidence remain
  required in both modes;
- optional explicit CPU evidence with a positive recommendation and rationale;
- supplied identity or known static values are rejected if they contradict the
  selected template.

The MCP boundary intentionally accepts no coefficient or tier override. It uses
`kposizing.DefaultConfig()` and returns that complete effective configuration
with every result so coefficients, limits, defaults, and supported tiers remain
auditable. Tool schemas expose the shared job-name length limit and the default
maximum number of file-evidence entries; the same limits are enforced at
runtime before catalog lookup.

Supported families are storage/API copy, threaded byte copy, chunked pandas,
whole-file pandas, change-detection concat, compressed base64 JSON, parquet to
CSV, and Spark CSV ingestion.

## Family formulas and evidence

`B` is the configured Python baseline, `J` is the Spark JVM baseline, and `U`
is upload serialization:

```text
U = serialization_factor × upload_concurrency × output_chunk_rows × output_row_width_bytes
```

All rational multiplier results are rounded upward to whole bytes.

| Family | Peak formula | Required evidence and semantics |
| --- | --- | --- |
| `storage_api_copy` | `B + API metadata + SDK duplication × largest file + optional API buffer` | `largest_file_bytes` or descending `file_bytes` is always required. A hybrid API path adds `api_buffer_bytes`; it does not replace largest-file SDK-buffer evidence. |
| `threaded_byte_copy` | `B + SDK duplication × sum(active file bytes)` | Supply descending `file_bytes`, or `top_concurrent_file_bytes` proving the complete active set at `copy_concurrency`. A partial top-N sample is not valid. |
| `chunked_pandas` | `B + changed source + unchanged source + frame_copies × effective_chunk_rows × in-memory row width + U` | Both complete source-cache sizes, in-memory row width, and upload fields are required. `effective_chunk_rows = min(row_count, chunk_rows)` when row count is supplied; otherwise it is configured `chunk_rows`. This safely handles datasets smaller than one configured maximum chunk. |
| `whole_file_pandas` | `B + largest source file + concat_factor × expanded bytes + U` | Largest-file evidence, complete expanded in-memory bytes, and upload fields are required. If row count or width is supplied, both are required and their product must equal expanded bytes. |
| `change_detection_concat` | `B + changed source + unchanged source + concat_factor × (changed expanded + unchanged expanded) + U` | Source and expanded bytes for both sides plus upload fields are required; a zero source must have zero expanded bytes. |
| `compressed_base64_json` | `B + encoded + decoded + output + max-row transient + U` | Encoded bytes and upload fields are required. Decoded and output bytes are required unless an explicit expansion ratio bounds each missing value. |
| `parquet_to_csv` | `B + largest partition + concat_factor × expanded largest partition + U` | `largest_partition_bytes` and `expanded_partition_bytes` describe the complete largest audit-selected `DatePartition` directory across all contained part files. `partition_count` and upload fields are required. |
| `spark_csv_ingestion` | `J + tasks/executor × (Spark factor × partition + cast/task + write/task) + shuffle/executor + cache/executor` | Executor count, tasks per executor, partition bytes, per-task cast/write bytes, and per-executor shuffle/cache bytes are required. The result is per executor; cluster peak is context. |

Catalog input scopes are evidence boundaries. A `HistoricalLatest` template
means the full `VersionPartition` root, not one convenient dated child.
Audit-selected parquet evidence must aggregate every part file within each
selected `DatePartition` before identifying the largest partition.

Catalog upload concurrency `10` means as many as ten output chunks are
serialized in one active batch, so `U` includes all ten concurrent chunks.

`get_kpo_job_templates` returns all 18 canonical templates in deterministic
order when `job` is blank. When `job` is non-blank, it returns one template and
normalizes documented aliases to the canonical job.

## Output semantics

The result includes:

- every peak-memory component and its exact bytes;
- peak, headroom, requested, and recommended-tier bytes;
- the requested unit (`runner` or `executor`);
- current and recommended CPU millicores plus the CPU rationale;
- evidence, assumptions, and warnings;
- the effective estimator configuration;
- the applied job template, when template mode was requested;
- human-readable GiB renderings that supplement, rather than replace, bytes.

For Spark CSV ingestion, the recommendation applies to each executor. The
response also reports executor count and estimated aggregate cluster peak as
context; it does not round the cluster total into one pod tier.

CPU is preserved unless explicit CPU evidence is supplied. Memory sizing is not
CPU evidence.
