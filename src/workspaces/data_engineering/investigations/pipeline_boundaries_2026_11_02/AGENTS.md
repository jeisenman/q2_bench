# Pipeline boundary evidence

This investigation retains synthetic Databricks differential results and source
pins for the Go workflow in `workflows/formalmethod/boundary_*.go`. It contains
no production records and does not execute application downloads, writes, or
copy tasks. All application Python behavior is evaluated remotely in Databricks.

Reproduce the source catalog and notebook preparation using
`docs/pipeline-boundary-tests.md`. Synchronize the published semantic graph and
require its exact di-pipelines commit. Keep code fragments, schemas, fixtures,
method IDs, and SOURCE digests pinned. Do not use an updated graph with old
source or reuse observations after method/input digests change.

At most ten scenario families apply per implementation and grouped logical
job. Isolated rows and clause checks are subcases within a scenario. Source
closure is conservative; explicit gaps and unclassified operations remain.
Plans, killed artificial IR mutants, isolated Spark agreement, and whole-job
coverage are separate evidence. No whole job passes in this investigation.

Preserve the first run's nested-field errors even though those operations are
now outside the primitive profile. Do not remove unsupported clauses from the
audit denominator or imply that a passing clause comparison validates complete
job execution or dataset distribution.

Retain the extension and initial projection runs, including signed-zero
transport and SELECT-star mismatches. Comparison v2 preserves negative zero
and adds a full-prediction digest; fresh v2 evidence supersedes earlier passing
records for reuse without erasing those earlier observations.

`fresh-v2-*-results.json` retain the three full v2 runs, including two metadata
model failures. `reusable-v2-0-results.json` explicitly selects the 598 unchanged
passing records from the first run. The other two runs are reusable in full.
`selection-v2-results.json` adds the final 60 matching cases. Together these
selected observations support `verified-v2-coverage.json`: 1,896 cases across
801 isolated clauses, zero failing/missing cases, and zero whole-job passes.
`verified-v2-execution.json` binds the run IDs, SOURCE and result-file digests.

`confidence-diagnostic.json` is an additional targeted clause subcase, not an
extra whole-job scenario. `confidence-results.json` retains all nine observed
Treasury D2P confidence examples. `impossible-findings.json` records the numeric
interval contradiction in the pinned source. The standalone report lives at
`work/pipeline-contradictions-20261102/pipeline-contradictions.html`; it labels
observed behavior, source contradictions, and unresolved business expectations
separately. No business rule is changed by these tests.

`comparable_contradictions.py` extracts only the pinned `handle_missing` helper
and its literal call arguments. `comparable-results.json` retains nine remote
subcases: two original zero-division errors, output dependence on selector order
and reused list state, threshold controls, and a rejected null-counter candidate.
`comparable-checks.jq` verifies those observations; this does not classify the
errors as valid business outputs. `comparable-findings.md` separates the two
confirmed defect classes from whole-job/deployment claims. Their evidence is
additional to the 1,896 Go/Spark comparisons; do not increase that pass count.
