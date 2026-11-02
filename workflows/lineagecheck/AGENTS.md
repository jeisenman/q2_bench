# Local structural lineage

## Architecture

This Go workflow owns reviewed structural manifests, source verification,
immutable local versions, PR compatibility, and backfill coverage. It uses
only the standard library and the existing `workflows/lineage` graph contract.
It does not import or inspect Researcher implementation code, execute Python
source, call a model, trigger Airflow, or query production data.

- `models.go` and `validate.go`: versioned contracts and fail-fast invariants.
- `schema.go`: a restricted lexer for literal primitive PySpark StructType
  schemas. Computed, nested, inherited, or mutated schemas require reviewed
  explicit fields; unsupported extraction fails rather than returning a subset.
- `build.go`: read Git blobs at full pinned commits, verify source SHA256,
  extract supported schemas, canonicalize, and content-address the snapshot.
- `store.go`: bounded reads, single-writer publication, immutable snapshot
  files, and atomic newest-first index updates. A crash may leave an unindexed
  valid snapshot or writer lock; inspect these before explicitly recovering.
- `compare.go`: additive compatibility and consumer-specific input replacement
  policies, including preserved column dependencies and historical evidence.
- `pr.go`: actual merge-base/head verification and changed-file coverage.
- `backfill.go`: column impact closure, conservative propagation for unknown
  columns, replay contract/date/client checks, and prerequisite ordering.
- `query.go`: projection and version history through the existing MCP surface.

## Workflow

1. Review source and update a manifest under `lineage/manifests/`. Every schema,
   column mapping, join/filter dependency, and replay rule belongs to an
   explicitly named scope/profile with pinned source evidence.
2. Build with explicit caller-supplied checkout roots. No working-tree source
   is read; a changed source digest requires a fresh contract review.
3. Dry-run before publishing to a scope-specific local snapshot store.
4. Compare baseline/candidate snapshots or a pinned replay plan. `fail` and
   `unknown` both fail the CLI gate; MCP returns the typed report status.
5. Serve the same store through `LINEAGE_STORE_PATH`, using existing lineage
   search, traversal, details, and history tools plus the comparison tools.

## Evidence limits

Manifests are reviewed contracts, not proofs that arbitrary application code
implements a contract. Literal schema extraction is automatic; column
transformations, row-affecting dependencies, DAG calls, copy scope, and replay
arguments are reviewed declarations tied to exact source bytes. Never change
only a digest to bypass review. `columns_complete` applies to declared output
projections within the named scope. Record unmapped work in `unresolved`.

Replay dates are inclusive output-date ranges, including every date in the
range. Monthly jobs use the month ends containing those dates. Sparse source
run sets and custom lookbacks need separate bounded plans or unresolved
findings. Plans describe expected invocation behavior, not execution results.
Historical availability and data equivalence require external evidence.

## Bounds and validation

Documents/source blobs are limited to 16 MiB; scopes to 32 repositories,
1000 datasets, 500 jobs, 1000 fields per dataset, and 10000 published versions.
Git operations have a 30-second timeout. Source repositories remain read-only.
Tests beside the package cover US Bank replay invariants, DE-3134 replacement
contracts, literal extraction failures, digest integrity, stale PR pins,
unknown coverage, and publication history. Run the repository quality command
and recreate MCP runtimes before behavior validation after changes.
