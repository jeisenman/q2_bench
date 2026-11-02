# Seeded pipeline property evidence

This investigation retains Databricks differential observations for the Go
property generator under `workflows/formalmethod/property_*.go`. It extends
the exact boundary evidence in `../pipeline_boundaries_2026_11_02/`.

Use the graph/source pin and generator configuration in `execution.json`.
Defaults are seeds 1, 42 and 20261102, with 32 additional rows per input table
per seed. Preserve the generator version and toolchain. Full generated inputs
are reproducible from the source-pinned boundary suite; runtime artifacts and
prepared notebooks live under `var/lineage/property-suite-20261102/`.

The property compares entire original-source Spark output row bags and column
names with independent Go predictions. Original boundary/empty inputs remain.
Synthetic relations only: no production records, downloads, uploads or copies.
At most ten scenario families still apply per implementation and logical job;
seeds and input rows are parameter instances inside those families.

Retain failed instances and source/method/input/prediction digests. Never infer
business-rule correctness from matching implementations, or universal coverage
from passing random samples. Unsupported source remains in the catalog. Exact
observations from the preceding investigation can be reused only while their
method, input and full prediction digests match. No whole job is certified.

See `docs/property-pipeline-tests.md` for generation, execution and replay.

The first campaign completed all six notebooks: 2,403 generated instances
matched, with no failures/errors. `ab-coverage.json` also verifies the reused
1,896 exact examples, for 4,299 matching comparisons and no missing evidence.
Whole-job status stays blocked. `property-*-results.json` retain the original
Jobs API result bodies; `execution.json` binds those files to runs, reviewed
notebook digests and generator/input receipts.
