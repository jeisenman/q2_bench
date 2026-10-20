# Production-support workflow

## Purpose

This package provides the deterministic production-support compatibility
workflow. Its control flow is fixed: no model chooses the next step.

Interactive live support follows
[`skills/prod-support`](../../skills/prod-support/SKILL.md), whose Markdown
procedure composes the Airflow and OMS MCP connectors directly in the current
agent, with required read-only Chrome inspection of both regional Airflow Task
Instances pages and the checked-in client UUID lookup JSON for identity
resolution. It first collects regional cluster health and active DAG counts,
then verifies every unique discovered DAG still exists before collecting task
evidence. The Chrome stage visibly applies the failed-task filters, expands
the `Search` panel, applies the `State = failed` and `Start Date > anchor`
filters, inspects all visible rows, and reconciles them with the typed MCP
inventory. It leaves both filtered regional result pages open for manual
operator inspection. Browser work uses Chrome browser-tab control only, never
native application or operating-system screen control. It does not route
failures to subagents.
Explicit compatibility and benchmark callers may still use `run_prod_support`.
Changed-dataset remediation uses a separate MCP path that dry-runs and clears
non-failed downstream tasks only in explicitly listed DAG runs. It does not
use Airflow's open-ended future-run expansion.

The default scope is US and CA for the previous operational day beginning at
05:00 UTC. Investigation is read-only. A developer follow-up authorizes
immediate execution of the exact eligible Airflow retries, and that is the
only production mutation in this package.

## Architecture

[`definition.py`](definition.py) declares the single public
`PRODUCTION_SUPPORT_DEFINITION`: a name, a description, a flat tool list, and
a pointer to the skill. It grants no delegation and names no subagents.

[`workflow.py`](workflow.py) is the composition root.
`ProductionSupportWorkflow.investigate` resolves the query window and scope,
runs the Airflow failure check and the cluster-health check concurrently,
hands the complete failure inventory to [`triage_manager.py`](triage_manager.py)
once, and formats reports from the result. It returns a `ProdSupportOutcome`
carrying structured findings plus the deterministic report text.

Evidence retrieval is layered cheapest-first.
[`investigation.py`](investigation.py) queries exact Airflow task metadata and
OMS before fetching a task log, and stops as soon as a cause is supported.
`max_parallel` bounds outbound API concurrency only; it must be at least 1 and
has no ceiling, because agent-loop parallelism is the harness's concern.

Reporting is deterministic. [`reporting.py`](reporting.py) and its
`reporting_*` modules render the combined, developer, and Data Internal
messages from findings. [`report_examples.py`](report_examples.py) holds the
compliant and non-compliant Data Internal lines that both the renderer and the
skill are written against. The narrative framing a reader sees is produced by
the harness from the skill, not by a model inside this package. All client,
DAG, run, and task identifiers remain complete in every audience.

[`harness.py`](harness.py) adapts the workflow to the shared
[`workflow_harness`](../../../../workflow_harness/) contracts, so the
`run_prod_support` MCP tool executes it through `WorkflowRunner` and records
the completed read-only stage. Stage side effects are declared there, which is
where the read-only boundary and the authorized-retry boundary are expressed.

[`retry_agent.py`](retry_agent.py) selects retry candidates deterministically
and `FollowUpExecutor` performs authorized retries against one exact task
identity. [`bench_builder.py`](bench_builder.py) writes a review-required
daily benchmark draft; it no longer defines a delegating agent, and new cases
are normally built from captured traces by the `benchmark-builder` skill.

## Dependencies

Domain values come from `domain`; typed contracts from `ports.py` in this
package and the top-level `ports` package. Concrete sources are injected at
the composition root in `mcp_servers/prod_support_sources.py`:

- `AirflowFailureSource` — the Airflow API in production, a replay dataset for
  captured evidence, or an empty source. Production connections come from the
  `produs` and `prodca` entries in `configurations.yaml`; a missing entry or
  value raises `AirflowConfigurationError` at startup.
- `ClusterHealthSource` — the read-only cluster script.
- The checked-in Resource Discovery UUID lookup JSON supplies exact client
  labels and environments for the Markdown-orchestrated live path.
- `OmsJobEvidenceSource` — DI_Scheduling_CL for Spark job evidence.
- `AgentMemory` — durable scoped summaries.

`PROD_SUPPORT_SOURCE` selects the capability transport: `direct` uses provider
adapters, `mcp` routes the same typed ports through dedicated read-only MCP
servers, `replay` uses captured benchmark evidence, and `empty` is the safe
local default. The mode changes transport only; workflow policy and report
rendering are identical, and integration tests require identical output from
`direct` and `mcp`.

This package depends on no agent framework and holds no model runtime. It must
not import from `workspaces.data_engineering.agents`, except for the
`oms_agent` query values it shares.

## Workflow

1. Resolve the operational anchor and the requested regions from the prompt.
2. Check Airflow failures ending at or after that anchor and check cluster
   health concurrently. Failure discovery has no upper cutoff so long-running
   tasks remain visible; cluster restart and recovery checks retain the bounded
   operational-day window.
3. Hand the full failure inventory to `TriageManager` in one call.
4. Resolve each failure from the cheapest sufficient evidence, escalating to an
   exact task log only when needed.
5. Verify both regional failure inventories through the read-only Chrome UI.
6. Resolve client identity from the checked-in complete UUID lookup JSON.
7. Render the combined, developer, and fixed-format Data Internal reports.
8. Compute retry candidates. Execution happens only on explicit developer
   authorization through `execute_prod_support_follow_up`. The MCP verifies
   all selected DAGs exist and are not paused; cluster health is retained as
   investigation evidence but is not a retry prerequisite. Exact task states
   are read through `get_task_instance_state`.
9. When corrected data affects later operational dates, plan exact per-run
   downstream recomputation through `plan_prod_support_dependency_rerun`.
   Execute only through `execute_prod_support_dependency_rerun` with the
   unchanged plan ID and explicit approval.

## Benchmark behavior

`benchmark_case_count("production-support")` is currently zero: the handoff
cases that scored the previous in-process orchestrator moved to
`benchmarks/deprecated/production_support/` when that orchestrator was
removed. The MCP warning reporting thin coverage is therefore accurate.
Rebuild coverage from captured traces with the `benchmark-builder` skill
rather than by restoring the retired cases.

## Verification

```bash
uv run python scripts/check.py
```

Tests mirror this package under
`tests/unit/workspaces/data_engineering/workflows/`.

## Change policy

Keep the control flow deterministic. If a change requires a model to decide
what happens next, it belongs in the skill, not here. Keep production mutation
confined to the authorized retry path, and never let a report claim a mutation
the returned evidence does not confirm.
