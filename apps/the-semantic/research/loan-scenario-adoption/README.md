# Loan scenario adoption research

## Question

Among managers who previously did not model alternative loan scenarios, does beginning sustained scenario modeling improve average return on equity and risk-adjusted profitability, relative to their own prior performance and comparable managers who have not yet adopted it? Report expected outcomes at pricing and realized outcomes after funding separately.

## Agreed outcomes

Average ROE and risk-adjusted profitability are co-primary. Expected performance
at pricing and realized performance after funding are separate outcomes.

## Current status

research.json is an unaccepted draft (accepted=false). The current CLI rejects it
before contacting the research API or invoking a model. The selected coordinator
is gpt-6.1-sol. rc now uses the managed runtime used by the working bc session;
older embedded-runtime rejections are not proof of missing Enterprise access.
There is no model substitution. Multi-agent dispatch and Databricks execution
are not implemented by the text-only MVP.

## Intended roles

- Sol 6.1: coordinate every experiment; complex mathematics, modeling and methods.
- Terra: browser control and tasks of moderate complexity.
- Luna: short ad hoc scripts and run submission.

The available exact worker model IDs must be checked before dispatch is enabled.
Each future worker attempt must pin its agent version and link to the same
experiment. The coordinator owns the accepted overall run/time budget.

## CLI sequence

From the project worktree, register the immutable coordinator definition:

```sh
./target/debug/researcher-codex agent put research/loan-scenario-adoption/agent.json
```

Review the research.json plan. Its first phase asks for a protocol, not a result.
Once that protocol request is accepted and 6.1 Sol access is available, change
accepted to true and run:

```sh
./target/debug/researcher-codex run --spec research/loan-scenario-adoption/research.json
```

The returned research_id retrieves the same record in CLI, MCP and the Research
catalog. Reusing an idempotency key retrieves existing evidence without another
model call. Changing content under the same existing key is a conflict; use a
new explicit key for a separately accepted revision.

## Decisions before empirical execution

Approved ROE/profitability definitions and weights; the manager/loan population;
adoption rule; pre/post and realized-observation windows; source fields and
permissions; minimum meaningful improvement; and a bounded execution budget.
No observational comparison alone establishes causality without supported
identification assumptions. Missing inputs must remain explicit.


## Refine the hypothesis first

The [Hypothesis Agent](../../agents/hypothesis/README.md) reviews six simple
criteria before planning. A [hand-written draft](../../agents/hypothesis/example.md)
preserves the selected outcomes and lists unresolved definitions without running
research. In a new rc session, ask it to use the Hypothesis Agent for this question.
