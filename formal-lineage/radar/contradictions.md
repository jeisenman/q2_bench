# Confirmed RADAR logic findings

The reviewed source contains a contradictory library subexpression and a
tautological notebook predicate. These are different logical findings.
RA preproduction confirmed both by executing the pinned original source:
110/110 library cases matched independent Go predictions; the eight notebook
cases all raised the portfolio error and then lost their errors at line 75.
The shared source catalogs still report unknown methods and
`prediction_ready: false`; these proofs do not imply complete RADAR lowering,
all-notebook coverage, deployed client reachability or whole-job equivalence.

## Library: an impossible conjunction in the scaling-factor fallback

[Read the condition proof and exhaustive truth table](scaling-factor-condition-proof.md).

Source: `radar_libraries/transform/loan_transform_helper.py`, commit
`6f72bfb32c447e92cf641a1dd4bcb2b94fac27f9`, lines 2063–2097.
The universal loan transform calls `get_adjustable_rate_values`, which calls
`_get_adj_rate_index_scaling_factor`.

Let F mean a scaling factor is present, T mean its import type is present,
and S mean the spread is present. The original source defines:

```text
bad_factors = (!F AND T) OR (F AND !T)
bad_spread  = F AND T AND !S
fallback    = (bad_factors AND bad_spread) OR !F
```

`bad_factors` requires exactly one of F/T; `bad_spread` requires both. Their
intersection is empty for all eight null-presence states. Consequently,
`fallback` simplifies to `!F`. The **conjunction arm** is unreachable; the
missing-factor arm still works.

Concrete counterexamples to the comment “default value for the failing records”:

| Factor | Import type | Spread | Bad pair | Bad spread | Default selected |
| --- | --- | --- | --- | --- | --- |
| 0.75 | missing | 0.01 | true | false | false |
| 0.75 | 0 | missing | false | true | false |
| missing | missing | missing | false | false | true |

The first two rows retain 0.75 and receive error messages; they do not reach the
1.0 default. This does not imply those errored records reach final datasets.
Changing AND to OR is a repair candidate that needs the intended fallback
contract reviewed; no source repair is included here.

## Notebook: a tautology flags every portfolio, then its errors are erased

Source: `notebooks/Shared/Clients/BOTW/Map_Others_BOTW.py`, commit
`60beb1ccd9bb2074f440de27e0e8f8956acab884`.
The normalized portfolio condition at line 63 is:

```python
(x != 'commcard') | (x != 'deposit')
```

For ordinary normalized strings, false would require x to equal both distinct
strings simultaneously. That state is impossible. The exhaustive comparison
partition is `commcard`, `deposit`, and every other string; the predicate is
true in all three classes. The predicate itself is a tautology, not a logical
contradiction; its negation is unsatisfiable. It conflicts with the stated
rule to ignore only unrecognized types. Both recognized portfolio types receive
“Ignored - do not recognize Portfolio Type” at line 64.

Line 70 also appends an inactive-account error, but line 75 then executes
`mapped_others["ErrorMessage"] = ""`, erasing both sets of errors. Do not
interpret the tautology as evidence that the final notebook rejects every row.
The validation defect is the sequence “flag everything, then clear the flags.”

The standard raw-file output contract includes ErrorMessage, so the reproduction
seeds it as an empty column. The BOTW extractor uses that standard outputter for
RawInputs_OtherFees. A separate missing-column control tests the helper's
precondition; actual client records and deployment configuration were not read.

## Reproduction and limits

The reviewed remote notebook selects original function definitions and exact
notebook statements using CPython AST; it never imports the application
modules or executes their I/O setup. It supplies the original error/log helpers
and constants from the same library commit, using synthetic data only.

The library campaign contains eight exhaustive null-presence cases, six
numeric-boundary controls, and 96 generated cases (seeds 1, 42, 20261103;
32 per seed). Go independently predicts masks, scaling-factor outputs and
error presence. These are three scenario families. The notebook exercises
four portfolio values crossed with two activity flags in one scenario family.
The comparison scope is those observations, not every output column or effect.

- [Boolean proofs, source receipts and truth table](../../src/workspaces/data_engineering/investigations/radar_contradictions_2026_11_03/proofs.json)
- [Investigation and regeneration](../../src/workspaces/data_engineering/investigations/radar_contradictions_2026_11_03/README.md)
- [Submitted RA run receipt](../../src/workspaces/data_engineering/investigations/radar_contradictions_2026_11_03/submission.json)

The [successful RA run](https://adb-7628572648057993.13.azuredatabricks.net/?o=7628572648057993#job/194334207777204/run/724838931862226) used Python 3.10.12, Pandas
1.5.3 and Spark 3.5.0. [Decoded original-source observations](../../src/workspaces/data_engineering/investigations/radar_contradictions_2026_11_03/results.json)
and [Jobs API child output](../../src/workspaces/data_engineering/investigations/radar_contradictions_2026_11_03/run-output.json)
retain the actual results. The impossible conjunction matched zero of 110
rows, including all eight null-presence states. All eight notebook errors
were cleared. No client records were read and no business implementation was
changed. Repository quality checks and the required MCP restart passed.
