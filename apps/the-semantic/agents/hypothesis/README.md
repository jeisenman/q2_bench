# Hypothesis Agent

A Sol 6.1 drafting role that converts a research question into a testable claim
and a short handoff to research planning. It asks one question at a time and
reuses answers already supplied. It does not test the hypothesis or start runs.

## Six simple criteria

| Criterion | What a good draft specifies |
| --- | --- |
| Specific | Population, unit, exposure, comparator, outcome, and claim type. |
| Measurable | Metric definitions, units, weights, exposure rule, and time window. |
| Falsifiable | Predicted effect, null/alternative, meaningful effect, and contrary evidence. |
| Credible comparison | Design, baseline, confounders, and assumptions needed for the claim. |
| Feasible data | Required sources, timing, sample/precision check, missingness, and leakage checks. |
| Prespecified and honest | Analysis/decision rules before testing; uncertainty, multiplicity, and exploratory labels. |

Each receives READY, MISSING, or CONTRADICTED with a reason. All six READY means
READY FOR PLAN REVIEW, not permission to execute and not proof of an effect.
Otherwise the status is DRAFT. Concrete feasibility checks can be planned before
data access; unverified facts must remain explicit. This rubric is our synthesis,
not a validated score. A null result is not proof of equivalence.

## Use

Register once from the application worktree:

```sh
./target/debug/researcher-codex agent put agents/hypothesis/agent.json
```

Restart rc to load its updated routing instructions, then ask:

> Use the Hypothesis Agent to refine my relationship-manager scenario-modeling
> question. Keep average ROE and risk-adjusted profitability as co-primary.
> Report expected and realized outcomes separately. Draft only; do not run it.

rc retrieves exact hypothesis version 1 through the existing MCP agent_get tool
and applies the role in the current conversation. There is no extra autonomous
worker, model call at startup, or new MCP surface. The retained agent appears in
Agent Catalog. Re-registering unchanged content returns the existing version;
changed content under that version is rejected.

The output is a draft, known decisions, a six-row review, minimal plan handoff,
and one next question. Its conversation is handled by the existing session
recorder. No separate persistent hypothesis entity or editable hypothesis form
is added in this change. See [example.md](example.md) for the first question.

## Research basis

Reviewed 2026-11-18. The rules below paraphrase primary methodological sources;
none supplies evidence that scenario modeling improves manager performance.

- [NIST: statistical tests](https://www.itl.nist.gov/div898/handbook/prc/section1/prc13.htm)
  supports a defined null, alternative, test procedure and error interpretation.
- [NIST: sample sizes](https://www.itl.nist.gov/div898/handbook/prc/section2/prc222.htm)
  explains why precision, effect size, variability and error risks inform sample needs.
- [J-PAL: randomized evaluations](https://www.povertyactionlab.org/resource/introduction-randomized-evaluations)
  explains comparison groups, causal attribution and feasibility limits.
- [Center for Open Science: preregistration](https://www.cos.io/initiatives/prereg)
  supports planning before testing, transparent deviations and separating
  exploration from confirmation, including held-out data.

The plain-language six-check structure and the loan-specific safeguards are
project design choices based on this guidance. They do not prescribe one
statistical method for every data-science question.
