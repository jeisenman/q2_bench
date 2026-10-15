# Data-engineering workflow harness

The workflow harness provides typed, provider-neutral contracts for executing
repeatable data-engineering workflows. Deterministic workflows own fixed
orchestration and policy; skills may own model-directed connector composition;
MCP servers and local adapters provide external capabilities; benchmark and
MLflow adapters measure behavior.

## Boundaries

- Skills translate user intent, compose typed connectors when model judgment is
  required, and explain approval requirements.
- Workflows declare ordered stages, allowed capabilities, and side-effect
  policy.
- Capability adapters access systems such as Airflow, OMS, Resource Discovery,
  package indexes, and source control.
- MCP exposes selected capabilities and complete workflow façades to external
  clients.
- Benchmarks replay bounded evidence and score outcomes without production
  access.
- Recorders receive bounded lifecycle events without prompts, logs,
  credentials, or arbitrary production payloads.

Core workflow code depends on the contracts in `workflow_harness`, not on MCP
or MLflow SDKs.

## Execution contract

`WorkflowRunner` validates authorization names, executes declared stages, and
returns typed output with the completed stages and workflow version. A stage
marked `approval_required` cannot execute unless its exact stage name appears
in `WorkflowRequest.authorized_stages`.

Implementations must execute work through
`WorkflowExecutionContext.run_stage`. Unknown, duplicate, overlapping, and
out-of-order stages fail immediately.

The runner emits bounded start, completion, and failure events through a
`WorkflowRecorder`. `NullWorkflowRecorder` is the default;
`InMemoryWorkflowRecorder` supports tests and local inspection. MLflow and
OpenTelemetry recorders belong in adapters.

`adapters.mlflow.publish_workflow_run` publishes a successful run's workflow
identity, completed stages, counts, and bounded lifecycle events. It validates
that the event sequence matches the result and deliberately does not log the
typed workflow output.

## Production-support integration

`ProductionSupportHarnessWorkflow` adapts the existing deterministic
`ProductionSupportWorkflow.investigate` boundary. Its current public stage is
`investigate`, and every declared capability is read-only:

- `airflow.read`
- `cluster.read`
- `resource-discovery.read`
- `oms.read`

The `run_prod_support` MCP tool executes this adapter through
`WorkflowRunner`. Existing reports, retry candidates, tool-call metadata, and
MCP fields remain compatible. The response attributes additionally identify
the workflow name, version, and completed stages.

Approved retry execution remains a separate MCP tool and is not part of the
read-only investigation workflow.

The interactive `$prod-support` skill uses a different composition boundary:
its Markdown procedure calls the Airflow, Resource Discovery, and OMS
capability tools directly, keeps all evidence reasoning in the current agent,
and does not delegate failures to subagents. `run_prod_support` is retained as
the deterministic compatibility façade for explicit callers and benchmarks;
it is not the default live skill route.

Production support supports these composition modes through
`PROD_SUPPORT_SOURCE`:

- `direct`: provider adapters call Airflow, OMS, and Resource Discovery.
- `mcp`: the same typed ports are implemented by dedicated MCP clients.
- `replay`: captured benchmark evidence is used without production access.
- `empty`: a safe local source returns no failures.

The direct and MCP compositions run the same production-support workflow.
Integration parity tests require identical reports, failures, diagnoses,
Resource Discovery results, and retry candidates. Retries are never exposed by
the Airflow capability server; they remain in the separate approval-gated
production-support follow-up tool.

## Capability MCP servers

Dedicated read-only servers expose provider facts:

- Airflow: `list_failed_task_instances`, `get_task_log`,
  `has_task_success`, and `get_task_metadata`.
- OMS: `query_oms` and `query_job_evidence`.
- Resource Discovery: `lookup_resources`, preserving zero, one, or multiple
  matches without resolving ambiguity.
- Dependency intelligence: `list_package_releases`,
  `check_python_compatibility`, and `list_dependency_changes`.

The dependency change tool reports bounded release-description markers for
compatibility, deprecation, removal, and breaking-change wording. These are
reported package facts, not an authoritative guarantee that every breaking
change was identified.

## Python-upgrade workflow

`PythonUpgradeWorkflow` separates policy from package facts. Its stages are:

1. `inventory`: read `pyproject.toml`, optional `uv.lock`, and a fingerprint.
2. `analyze`: check direct locked dependencies with at most five workers.
3. `plan`: produce blockers, unknowns, and dependency updates.
4. `apply`: update the Python minimum and regenerate `uv.lock`.

The first three stages are read-only. `apply` requires explicit stage
authorization and the exact inventory fingerprint. It refuses blockers,
unknown package support, and dependency updates that still require review.
Lock-generation failures restore the original project files.

The Python-upgrade MCP server keeps planning and mutation as separate tools:
`plan_python_upgrade` and `apply_python_upgrade`.

## Benchmarking

Production-support capability parity is checked against the same deterministic
workflow output. The Python-upgrade benchmark covers a safe plan, a required
dependency update, missing compatibility metadata, and stale-plan rejection.
Workflow lifecycle metadata can be published to MLflow without uploading
prompts, logs, project files, credentials, or arbitrary provider payloads.
