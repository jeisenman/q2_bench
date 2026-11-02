# Seeded pipeline properties

Pipeline validation supports generated, reproducible property instances
alongside exact boundary examples. The property compares the entire
Go-predicted output row bag and column names with original source executed
in Databricks. It retains duplicates and null behavior. Matching source does
not establish that its business rule is correct.

For `x > 0`, exact below/equal/above values and adjacent representable numbers
remain in the input. Seeded instances add values and combinations around
source-derived domains. Nulls, duplicates, ASCII strings, booleans and shared
named join keys vary. Empty-input cases remain explicit examples. Inputs retain
the supported primitive schema and source-literal bindings.

## Generate

```bash
go run ./cmd/agentbench formal-method property-suite \
  --suite var/lineage/boundary-suite-final-20261102 \
  --output var/lineage/property-suite-20261102 \
  --seeds 1,42,20261102 --samples 32
```

The defaults are three recorded seeds and 32 additional rows per input table
per seed. Counts are explicit, not a statistical confidence guarantee. Each
supported clause receives one instance per seed, using its largest exact
fixture as the base. Original boundary/empty cases are retained without edits.
Seeds and rows are parameter instances within existing scenario families; the
ten-scenario-family limit per implementation and logical job is unchanged.

Bounds are 1–16 distinct unsigned seeds and 1–256 additional rows per table.
Invalid counts and unsupported schemas reject generation. Requested counts
are never silently reduced. Output/compute bounds still apply; a join exceeding
the existing evaluator limit blocks preparation. Split comparison notebooks
to satisfy their size bound without reducing the input sample count.

The initial suite has 2,403 seeded instances across 801 supported clauses plus
1,896 exact examples. Other clauses and whole jobs remain blocked. Generation
alone is not a Databricks pass.

The first execution confirmed all 2,403 generated instances in Databricks
Spark 4.1.0. With the exact examples, all 4,299 comparisons match across the
801 supported clauses: zero failures, errors or missing observations. Receipts
and results live in the workspace investigation `pipeline_properties_2026_11_02`.
Whole-job passes remain zero. These counts describe this seed/sample campaign,
not every possible input or the correctness of the source business rules.

## Execute and replay

Use `boundary-pending`, `prepare-boundary-comparison` and `boundary-evidence`.
Reuse exact verified boundary observations only; generated cases need fresh
Databricks observations. Run original source on the same synthetic input,
following the remote-data review and submission procedure. Retain every failing
input and error, not just passing seeds.

Each case records the generator version, seed, sample count, base case ID,
complete input, source receipt and schemas. The PCG stream derives from this
identity plus the table name. Sorted table names make generation independent
of Go map iteration. Adding unrelated clauses does not change existing inputs.
Source changes deliberately change case identity.

Loading replays generation and rejects altered inputs or metadata. Input and
prediction digests bind Databricks evidence to the exact comparison. Recreate
the same suite with the recorded command to replay a failure. Automatic
counterexample shrinking is not implemented.

Compiler/evaluator regression tests still test the harness, including parser
failures, unsupported constructs and deterministic replay. Pipeline properties
extend validation beyond handpicked job fixtures. Business invariants need
independently reviewed oracles. Whole-job reachability, physical copies and
dataset distribution remain outside isolated-clause equivalence.
