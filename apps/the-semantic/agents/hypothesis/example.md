# First research question: hypothesis draft

This is a hand-written example of the expected format. It is not a model output,
a dataset analysis, or evidence that the proposed effect exists.

## Status

DRAFT. The user has selected outcomes, but operational definitions and a credible
comparison still need agreement. Nothing here accepts or starts an experiment.

## Known decisions

- Question: Does starting loan-scenario modeling improve a relationship manager's performance?
- Co-primary measures: average return on equity and risk-adjusted profitability.
- Expected outcomes at pricing and realized outcomes after funding remain separate.

## Draft hypothesis

For eligible relationship managers who previously did not model alternative
loan scenarios, beginning scenario modeling is associated with improved average
ROE and risk-adjusted profitability over a defined follow-up window, relative to
their prior performance and a comparable group that has not yet adopted it.

The intended research question is causal. The current draft uses association
until a defensible design and its identification assumptions are specified.
A proposed mechanism is that comparing alternatives improves pricing choices;
this is a hypothesis, not an observed explanation.

Evaluate four endpoint series separately: expected ROE, expected risk-adjusted
profitability, realized ROE, and realized risk-adjusted profitability. For each,
let tau be the adopter/comparator change contrast under the selected design.
A directional statistical draft is H0: tau <= 0 versus H1: tau > 0. A causal
interpretation requires additional assumptions; tau is not automatically an
identified treatment effect. The smallest meaningful change remains TBD for
each endpoint, as do uncertainty and joint interpretation rules. An inconclusive
interval does not establish either benefit or equivalence.

## Six-criterion review

| Criterion | Status | Reason |
| --- | --- | --- |
| Specific | MISSING | Manager population, comparator eligibility and exposure rule are not fixed. |
| Measurable | MISSING | Outcome names are known; approved formulas, units, weights and windows are not. |
| Falsifiable | MISSING | Direction is drafted; meaningful effects and decision rules are unresolved. |
| Credible comparison | MISSING | A comparison is proposed; assignment, confounders and assumptions are unverified. |
| Feasible data | MISSING | Scenario history, manager attribution, metric provenance and power are unverified. |
| Prespecified and honest | MISSING | Analysis, multiplicity, missingness and stopping rules remain to be reviewed. |

## Minimal research-plan handoff

Propose a manager-by-time study, retaining opportunity/loan-level provenance.
Identify adoption only from information available before the outcomes being
attributed to it. A future sustained-use requirement can create selection bias
if it is used to classify earlier observations as treated.

Check scenario history, responsible manager versus editing actor, approved
pricing metrics and realized outcomes. Count opportunities, not each saved
scenario, as loan observations. Verify loan/risk mix, calendar conditions,
manager experience, changing metric/model definitions, funded-only selection,
and equal follow-up maturity. Repeated loans from one manager are not independent
manager observations. One manager does not establish a population-wide effect.

Then specify a feasible comparison and precision assessment, four endpoint
interpretation/multiplicity rules, exclusions, missingness, intervals, thresholds
and stopping rules before testing. If outcomes have already informed the claim,
label it exploratory and reserve independent data for confirmation. Report
negative or inconclusive findings. Data access and execution remain unaccepted.

## One next question

What observable scenario-modeling activity should count as adoption by a
relationship manager?
