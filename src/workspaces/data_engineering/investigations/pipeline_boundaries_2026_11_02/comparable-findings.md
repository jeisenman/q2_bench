# Two additional confirmed transform defects

Databricks executed the original `handle_missing` function at di-pipelines
commit `20822fe0d10e812d9858d4ec6d550cce1340cac9`, using synthetic Spark inputs.
The source file is
`ds-jobs/src/datascience_jobs/jobs/data/market_insights/comparable_loans_training_data.py`.
Its SHA256 is `69f53c4af196064a0abcc7fe2915bc0e440e26908f1b842d3cca48c3f9773ea0`.
The notebook extracts that one function with CPython AST and copies its literal
`COLS_TO_IMPUTE` and `NULL_CUTOFF` arguments. It imports no application modules,
reads no production records, and executes no application uploads or writes.

## Zero-row guards still divide by zero

The Python scalar guards at lines 476 and 489 use bitwise OR. Both operands
evaluate, so the right operand divides by zero even when the left operand
already establishes a zero-sized applicable population.

| Synthetic population | Original outcome | Source line |
| --- | --- | --- |
| Two Fixed-rate loans, both LOC | `ZeroDivisionError` | 476 |
| Fixed + Float loans, neither LOC | `ZeroDivisionError` | 489 |
| Fixed + Float loans, both LOC | Returns normally | control |

This confirms one defect class in two guards. It is a Python scalar evaluation
problem; Spark column OR expressions are a separate API and are not implicated.

## A shared list makes missing-feature treatment depend on order and history

At lines 465–491, `cols_to_keep = col_list` aliases the caller's list, then
the helper removes entries while iterating `col_list`. A removal shifts the
next entry past the iterator, skipping its missingness check. The final fill
step treats that skipped entry as a feature to impute.

The source documents that features above the missing-fraction cutoff should
be nulled. With both standardized term features entirely null and the actual
source cutoff of 0.33, both should remain null under that documented rule.

| Original helper execution | StdLogTerm | StdLogAmortizationTerm |
| --- | --- | --- |
| Actual source column order, first call | null | **0.0** |
| Reverse just those two selectors | **0.0** | null |
| Same input and original list object, second call | null | null |

All rows show these values. Changing selector order changes which feature is
silently imputed. Reusing the mutated list changes the result on the same
input. The actual caller passes the module-level list at line 642; this
experiment uses a copy for isolation, then deliberately reuses that copy.

## Controls and boundaries

Nine diagnostic subcases cover the ordinary return, both zero-population
failures, adjacent all-null features, reversed selectors, repeated invocation,
and missing fractions below/equal/above the selected cutoff. Repeated invocation
is a subcase of the adjacent-feature test. Exactly 50% missing with cutoff 0.5
is imputed; the same rows with cutoff 0.49 are nulled and with 0.51 are imputed.
The original counter correctly counts null plus NaN: the string passed as the
WHEN result is a literal column-name string, not the null column value.
That initially suspicious counter is excluded as a defect.

These checks belong to the existing null/branch/arithmetic scenario families,
not extra whole-job scenarios. They are source/helper reproductions, not new
Go formal-method equivalence cases or certification of deployed jobs. The
repository job is in the combined inventory, with no published graph job ID.
Full upstream reachability and deployed revision remain unverified.

## Evidence

- [Databricks reproduction run](https://adb-3510128597187204.4.azuredatabricks.net/?o=3510128597187204#job/522124915654227/run/298836884447837)
- `comparable-results.json`: original observations, including the two errors.
- `comparable-execution.json`: source/notebook/result digests and run receipts.
- `comparable_contradictions.py`: reviewed notebook source with pinned source.
- `comparable-checks.jq`: mechanical assertions for reproductions and controls.

Recheck the retained observation assertions without rerunning application code:

```bash
jq -ef comparable-checks.jq comparable-results.json
```

No pipeline business rule has been changed.
