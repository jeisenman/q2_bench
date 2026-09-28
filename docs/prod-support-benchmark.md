# Production-support agent and benchmark

The public production-support package is:

```text
src/workspaces/data_engineering/agents/production_support/
```

It keeps the explicit prdbench agent graph and the reusable operational tools
from both earlier folders. `ProductionSupportWorkflow` is an internal executor,
not an additional public agent.

## Agent graph

Orchestrator coordinates these named subagents:

- ClusterAgent checks scoped US and CA cluster health.
- AirflowAgent runs the baseline failure script, uses baseline results for
  omitted jobs, and analyzes non-omitted failures.
- TriageAgent currently returns `Triage agent hasn't been setup.`
- FollowUpAgent plans exact retries and executes only an unchanged approved
  plan.
- Reporter renders the authoritative production-support response.
- BenchBuilderAgent creates a redacted, review-required benchmark draft when
  the user requests production support and benchmark construction together.

Prompts are explicit function docstrings in
`production_support/prompts.py`. Tool assignments are defined by
`production_support/suite.py`; operational tool metadata remains in
`production_support/tools.py`.

## Date and scope semantics

Production support defaults to both US and CA and the previous operational day.
The operational window begins at 05:00 UTC. Explicit region or date requests
override those defaults.

Airflow discovery uses task end time so long-running failures ending in the
window are included. Regional findings and client identities must remain
separate throughout the handoffs.

## Active benchmark

The stable manifest is:

```text
src/workspaces/data_engineering/benchmarks/production_support/manifest.yaml
```

It contains one active run:

```text
dates/09-27-26/
```

This run was built on September 27, 2026 for the September 26 operational day.
Removed v1 runs are not retrofitted to current expectations.

The suite includes focused cases for ClusterAgent, AirflowAgent, TriageAgent,
FollowUpAgent, Reporter, and BenchBuilderAgent. Handoff contracts measure:

- required named agents and parent attribution;
- exact input and output fields;
- call cardinality and dependency ordering;
- parallelism and leaf-agent delegation boundaries;
- Reporter output authority;
- retry and production-mutation safety;
- benchmark draft quality; and
- continuity of normal MCP output fields.

ClusterAgent and AirflowAgent may run concurrently. Reporter starts after both.
BenchBuilderAgent starts after Reporter and may add artifact metadata, but it
must not replace or rewrite the production-support output.

## Matrix validity and scoring

Before any candidate model or judge is invoked, the matrix runner stages the
declared evidence inputs and executes the same compact-evidence command inside
the configured runtime. A missing module, malformed dataset, or failed parser
invalidates the run immediately and produces no candidate score or token use.

Every case declares a complete applicability map using the rubric criterion
IDs. Unknown or missing criteria fail manifest loading. The runner recomputes
the weighted overall score from applicable criteria only; inapplicable criteria
cannot inflate or reduce the result.

Named handoff contracts measure agent identity, parent attribution, payloads,
cardinality, delegation boundaries, and output authority. Ordering remains in
the agent prompt as expected operational behavior but is not a scored contract.
The container runtime explicitly enables Codex multi-agent tools so candidates
can produce genuine handoff traces.

## Dataset lifecycle

Sensitive working captures remain ignored under:

```text
var/benchmark_data/production_support/YYYY-MM-DD/
```

Only reviewed, minimized, redacted evidence belongs in a dated source suite.
Raw logs, credentials, hidden expectations, and unrelated customer data must
not be committed.

For the complete collection procedure, see
[Prod-support daily data collection](prod-support-data-collection.md).

Useful commands:

```bash
uv run agentbench debug-prod-support --date 2026-09-26

uv run agentbench run-matrix \
  --benchmark src/workspaces/data_engineering/benchmarks/production_support/dates/09-27-26/evaluation.yaml \
  --cases src/workspaces/data_engineering/benchmarks/production_support/dates/09-27-26/cases.yaml \
  --case handoff-bench-builder-agent-2026-09-26 \
  --execute

uv run python scripts/check.py
```

Benchmark construction is read-only and produces a draft requiring independent
review. It does not authorize FollowUp execution.
