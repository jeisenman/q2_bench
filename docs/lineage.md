# Local lineage and compatibility checks

qtwo_bench owns structural lineage manifests, immutable local versions, and
backfill/PR comparisons. Go reads source blobs at full Git commits; it never
executes the application code. Researcher is optional for the separately
imported graph and generated business descriptions.

## What is automatic and what is reviewed

A manifest under `lineage/manifests/` specifies a scope, client/feature profile,
source repository commits, logical datasets, consumed columns, transformations,
DAG task identities, ordering, and replay rules. Each declaration references
source paths and SHA256 digests. Builds reject missing or changed evidence.

The extractor automatically reads literal primitive PySpark `_schema_vN`
StructType methods selected by class/version. Explicit fields supplement those
schemas, for example writer-added DatePartition. Unsupported computed,
inherited, nested, or mutated schemas fail extraction; use reviewed explicit
fields instead. Types use names such as `StringType` and `DoubleType`.

Column mappings and replay rules are reviewed declarations pinned to source
bytes. The tool does not infer arbitrary Spark transformations or Python DAG
execution. Include value dependencies and row-affecting filter/join/grouping
columns. Input `keys` conservatively affect every output column. Empty
`Dependency.inputs` declares a constant output. `columns_complete` asserts
coverage of declared output projections within the named scope. Put missing
coverage in `unresolved`; do not silently omit it.

A passing report establishes compatibility within that reviewed scope. Runtime
row counts, join cardinality, historical availability, and data equivalence
require separate validation evidence.

## Build and retain local manifests

The checked-in DE-3134 example covers a deposit metadata projection and its
`IndustryCode -> NaicsCode` alias. It retains the retired dataset while moving
the selected consumer, and automatically extracts both metadata schemas.

```bash
go run ./cmd/agentbench lineage build \
  --manifest lineage/manifests/de-3134-base.json \
  --repo di-pipelines=../di-pipelines --dry-run

go run ./cmd/agentbench lineage build \
  --manifest lineage/manifests/de-3134-base.json \
  --repo di-pipelines=../di-pipelines --store var/lineage/de-3134

go run ./cmd/agentbench lineage build \
  --manifest lineage/manifests/de-3134-head.json \
  --repo di-pipelines=../di-pipelines --store var/lineage/de-3134
```

Use the emitted `snapshot_id` values as BASE and HEAD below. Source commits
must exist in the supplied checkout; the checkout itself is not changed.
Builds ignore uncommitted working-tree modifications. Update the source pin,
review the changed source and contracts, and refresh affected digests together.
Repeated publication of the same content is idempotent.

Stores contain `snapshots/<SHA256>.json` and an atomically published
`index.json`. Keep a separate store per scope/profile. Use `lineage show
--store PATH --snapshot ID` to inspect a complete verified manifest. Omitting
the ID selects the latest snapshot for `show` only. No database or Researcher
installation is required.

## Compare changes and check a PR

```bash
go run ./cmd/agentbench lineage compare \
  --store var/lineage/de-3134 --base "$BASE" --head "$HEAD"

go run ./cmd/agentbench lineage compare \
  --store var/lineage/de-3134 --base "$BASE" --head "$HEAD" \
  --policy lineage/policies/de-3134.json

go run ./cmd/agentbench lineage check-pr \
  --store var/lineage/de-3134 --base "$BASE" --head "$HEAD" \
  --policy lineage/policies/de-3134.json \
  --repository di-pipelines --root ../di-pipelines \
  --base-ref origin/master --head-ref origin/DE-3134
```

The default additive policy preserves existing fields, versions, keys,
partitions, job inputs/outputs, column mappings, and prerequisite ordering.
Compatible field additions and minor-version increases are allowed. A
replacement policy permits only named consumer/input changes, optionally
mapping old field names to new ones. It checks the fields actually consumed,
join keys, and preserved output dependencies. Historical migration status and
its evidence must be supplied; the checked-in DE-3134 policy deliberately
leaves that status unverified.

`check-pr` additionally requires the source pins to match the actual merge
base and head. Every changed file must have source evidence in the selected
contract scope; uncovered files produce unknown findings. The example is a
consumer slice, so it cannot certify the full DE-3134 PR without expanding
coverage. Use this command as a CI gate in the source repository with a pinned
qtwo_bench checkout and reviewed base/head manifests. No GitHub check or PR
comment is posted automatically.

Both `fail` and `unknown` exit nonzero after printing the complete JSON report.
An invalid input exits immediately with an actionable error.

## Compare a backfill

```bash
go run ./cmd/agentbench lineage build \
  --manifest lineage/manifests/us-bank.json \
  --repo di-pipelines=../di-pipelines --store var/lineage/us-bank

go run ./cmd/agentbench lineage backfill \
  --store var/lineage/us-bank --snapshot "$SNAPSHOT" \
  --plan lineage/backfills/us-bank.json
```

The plan pins the snapshot and client, repaired dataset/columns, inclusive
historical output-date range, and reviewed replay invocations with their own
source evidence. An empty columns array selects all declared source columns.
Evidence for every invocation must already be pinned on a snapshot job.

Checks compute the affected column closure through transformations, copies,
and reporting outputs. Incomplete column mappings conservatively affect every
output and produce unknown findings. Data dependencies and declared ordering
both constrain replay order, including across child DAGs.

The replay contract checks partition/window/month-end/cross-client mode,
scheduled UTC hour, replace writes, forced replay, schedule-gate overrides,
client scope, and exact
historical output dates. Monthly jobs require the corresponding month ends.
The current plan format describes contiguous date ranges; sparse partitions
and custom lookbacks require separate bounded plans or unresolved findings.

The US Bank example covers a deposit-balance projection, its copies, monthly
output, and LOC aggregation. It deliberately reports the deferred LOC replay
and an unresolved full-remediation closure. Its sample dates are regression
inputs, not the authoritative corrected source-run manifest. This is not
production completion evidence.

## Existing MCP surface

The `lineage` and `prod-support` servers expose the existing search, traversal,
transformation, and history tools plus:

- `get_lineage_manifest`: inspect a local immutable version and source pins.
- `compare_lineage_versions`: additive or replacement compatibility reports.
- `compare_lineage_backfill`: coverage and replay-contract reports.

Set `LINEAGE_STORE_PATH` to serve local versions through all lineage tools.
Inside Compose, use a path under `/workspace/var` and recreate the affected
server after changing configuration. The comparison tools default to
`var/lineage/local` when the variable is absent. Filesystem paths are selected
by server configuration; callers supply snapshot IDs, not arbitrary paths.

With no local store selected, query tools preserve the imported
`LINEAGE_GRAPH_PATH` behavior, defaulting to `var/lineage/di-pipelines.json`.
Local history uses the newest published versions in the active scope/profile;
the imported single-file source exposes only its current graph version.

## Optional Researcher snapshot

```bash
go run ./cmd/agentbench semantic-sync --dry-run
go run ./cmd/agentbench semantic-sync
```

The sync validates the complete published contracts, request digest, exact
node coverage, and provenance before atomically staging generated meaning as
`q2_semanticMeaning`. No Researcher implementation is imported. Meaning is
retained on the imported graph; it is not automatically copied onto changed
local nodes or used as compatibility evidence.
