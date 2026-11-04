# Proof: the scaling-factor error-mask intersection is empty

**Claim:** In the original RADAR library, `bad_factors_condition &
bad_spread_condition` cannot be true. The separate missing-factor fallback
can still be true.

This is a proof of an unreachable subexpression. Treating its replacement
with OR as a business-rule correction additionally assumes the comment's
policy: incomplete settings should receive the default factor.

## Pinned source

Repository: `precisionlender/radar-libraries`  
Commit: `6f72bfb32c447e92cf641a1dd4bcb2b94fac27f9`  
Function: `_get_adj_rate_index_scaling_factor`  
[Original conditions and fallback](https://github.com/precisionlender/radar-libraries/blob/6f72bfb32c447e92cf641a1dd4bcb2b94fac27f9/radar_libraries/transform/loan_transform_helper.py#L2063-L2097)

Let:

- **F** = scaling factor is present.
- **T** = scaling-factor import type is present.
- **S** = adjustable-rate spread is present.

The original masks translate to:

```text
bad_factors = (!F AND T) OR (F AND !T)
bad_spread  = F AND T AND !S
intersection = bad_factors AND bad_spread
```

The first mask requires exactly one of F/T. The second requires both.
Therefore their intersection is false for every assignment.

## Exhaustive truth table

| F | T | S | bad_factors | bad_spread | intersection |
| --- | --- | --- | --- | --- | --- |
| false | false | false | false | false | false |
| false | false | true | false | false | false |
| false | true | false | true | false | false |
| false | true | true | true | false | false |
| true | false | false | true | false | false |
| true | false | true | true | false | false |
| true | true | false | false | true | false |
| true | true | true | false | false | false |

Consequently, the complete original fallback simplifies as follows:

```text
(bad_factors AND bad_spread) OR !F
= false OR !F
= !F
```

## Runtime evidence

RA preproduction executed the pinned original definitions with synthetic data:

- All eight null-presence states above were exercised.
- Six numeric-boundary controls and 96 seeded cases were also checked.
- All 110 cases matched independent Go predictions.
- Zero rows satisfied the intersection.

For factor `0.75`, a present import type and a missing spread, the original
function flags an error but retains `0.75`; it does not select the `1.0`
default. For a missing factor, the outer `!F` arm selects `1.0` as before.

[Machine-readable truth table and source hashes](../../src/workspaces/data_engineering/investigations/radar_contradictions_2026_11_03/proofs.json)  
[Observed values and error messages](../../src/workspaces/data_engineering/investigations/radar_contradictions_2026_11_03/results.json)  
[Jobs API child output](../../src/workspaces/data_engineering/investigations/radar_contradictions_2026_11_03/run-output.json)  
[Reproducible source preparation and notebook](../../src/workspaces/data_engineering/investigations/radar_contradictions_2026_11_03/README.md)

The proof establishes the unreachable intersection and the observed fallback
behavior. It does not independently establish the intended business policy,
prove whole-job equivalence, or show that errored records reach final datasets.
[The proposed OR replacement](https://github.com/precisionlender/radar-libraries/pull/655)
is a separate change for review.
