---
name: lineage-review
description: Maintain local source-pinned lineage manifests, check additive or replacement PR compatibility, and compare column backfills with required downstream replay coverage.
---

# Local lineage review

Use the Go workflow documented in `docs/lineage.md`. The canonical manifests,
replacement policies, and replay plans live under `lineage/`. Researcher is
optional; its descriptions are not compatibility evidence.

## Maintain a manifest

Choose an explicit product/column scope, environment/client/feature profile,
and full source commit pins. Inspect the source at those pins. Dataset identity
includes its logical stage and path; changing an input dataset creates a new
identity, not an alias for the retired dataset.

Build with `agentbench lineage build --manifest PATH --repo NAME=CHECKOUT
--dry-run`, then publish to a scope-specific store. Literal primitive PySpark
schemas can be extracted using `schema.evidence`, `class`, and `major`. Declare
writer-added columns explicitly. For computed schemas, maintain reviewed
explicit fields with exact source evidence.

Review mappings, filters, joins, grouping keys, copies, versions, and output
partitions. Record source SHA256 values from pinned Git blobs. Refresh a digest
only after reviewing the changed behavior and updating its contract. Set
`columns_complete` only when all declared output columns have dependency
entries. Include row-affecting inputs on affected outputs; input keys affect
all output rows. Record missing scope or unresolved behavior in `unresolved`.

## Check a PR

Build snapshots at the actual Git merge base and PR head, with other source
repository pins held constant. Run `lineage check-pr` with both snapshot IDs,
repository name, checkout root, and destination/source refs. Its changed-file
coverage check must not be bypassed by reusing stale snapshots.

Use additive mode when old contracts remain intact. For an input replacement,
list each consumer and old/new dataset in a replacement policy. Verify consumed
columns and aliases, types/nullability, join keys, major versions, partitions,
producer ordering, and downstream output contracts. Keep the retired dataset
until a separately reviewed retirement covers all consumers. Verify historical
availability with an attributable validation artifact; do not mark history
verified from the source diff alone.

`lineage/manifests/de-3134-*.json` and `lineage/policies/de-3134.json` demonstrate
the supplemental-data to metadata swap and `IndustryCode -> NaicsCode` mapping.
They cover a selected consumer projection, not the whole PR.

## Compare a backfill

Pin the structural snapshot, client, affected dataset/columns, and historical
output dates. Inspect the actual backfill DAG, task groups, child DAGs, and
runner behavior before describing invocations in a plan. Pin their source
files as snapshot job evidence. Run `lineage backfill` or the existing
`compare_lineage_backfill` MCP tool.

Include primary/derived processing, copies, reports, cross-client products,
monthly outputs, and prerequisite order within the requested scope. Distinguish
partition filtering from normal update discovery: a corrected source retaining
its RaRunId may require forced replay. Preserve scheduled output-window hours,
including the US Bank 05:00 UTC convention; month-end jobs need month-end output
dates and schedule gates overridden. The current date-range contract is
contiguous; record sparse partition sets/custom lookbacks as unresolved or
use separately bounded plans. Disabled/deferred consumers remain coverage gaps.

The US Bank examples deliberately retain the deferred LOC replay and missing
full-remediation coverage. Their dates are regression examples, not an approved
production source-run manifest.

## Interpret and report

Report scope, source pins, affected columns, required/missing jobs, incompatible
contracts, and unresolved evidence. `unknown` blocks passing just as `fail`
does. A passing static report applies only to its reviewed scope; it does not
prove runtime data equivalence, historical existence, or successful execution.
Do not turn a passing report into deployment or Airflow execution authority.
No external comments or notifications are sent by this workflow.
