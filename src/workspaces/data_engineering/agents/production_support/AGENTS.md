# Production-support agent

## Purpose

This package keeps the explicit prdbench agent design as the public
production-support system while retaining the operational tools from the
earlier implementation. The public graph consists of Orchestrator,
ClusterAgent, TriageManager, FollowUpAgent, Reporter, and BenchBuilderAgent.

The default production-support scope is US and CA for the previous operational
day beginning at 05:00 UTC. Normal investigation is read-only. A developer
follow-up authorizes immediate execution of the exact eligible Airflow retries.

## Architecture

[`prompts.py`](prompts.py) defines every agent prompt in a function docstring.
[`definition.py`](definition.py) converts named prompts and tool assignments
into typed `AgentDefinition` values. [`suite.py`](suite.py) constructs the
public graph and is the only module that grants delegation to Orchestrator.
All operational specialists are leaf agents. BenchBuilderAgent may perform
bounded benchmark-review delegation, but total parallelism must not exceed
five.

Tool ownership is explicit:

- ClusterAgent receives the read-only cluster-health tool.
- TriageManager receives the complete failure inventory once and owns failure
  discovery, exact-log, workload, OMS, classification, and Resource Discovery
  tools. It stops when cheap evidence resolves a cause and fetches detailed
  logs only for unresolved failures.
- FollowUpAgent receives the exact retry execution tool.
- Reporter receives evidence-qualified findings and calls no investigation
  tools.
- BenchBuilderAgent receives completed handoffs and builds a redacted,
  review-required current-day benchmark draft.

[`workflow.py`](workflow.py) retains the deterministic operational workflow as
`ProductionSupportWorkflow`. It uses the same public Orchestrator definition
but executes the existing injected adapters and domain logic. The reusable
implementation remains split across date, scope, cluster, Airflow,
investigation, classification, reporting, retry, dataset, and port modules.
[`harness.py`](harness.py) adapts that investigator to the shared
`workflow_harness` contracts. The `run_prod_support` MCP façade executes the
adapter through `WorkflowRunner` and records the completed read-only stage
without changing the authoritative report or retry-candidate contract.
The MCP composition root selects `direct`, `mcp`, `replay`, or `empty`
capability sources. In MCP mode, Airflow, OMS, and Resource Discovery remain
behind the same typed ports and execute through dedicated read-only servers.
Direct and MCP integration tests require identical authoritative output.
Shared OMS routing, query construction, and evidence protocols are owned by
[`../oms_agent/`](../oms_agent/); this package retains compatibility exports.
It is an internal workflow, not a second public agent.

OpenTelemetry spans mirror execution: MCP is the root, Orchestrator
investigation is its child, delegated Resource Discovery and reporting are
children of investigation, and provider runtime calls are children of
reporting. TriageManager has one batch span; follow-up execution has its own
agent span.

```mermaid
flowchart LR
    Request --> Orchestrator
    Orchestrator --> ClusterAgent
    Orchestrator --> TriageManager
    ClusterAgent --> Reporter
    TriageManager --> Reporter
    Orchestrator --> FollowUpAgent
    Reporter --> FinalOutput
    Reporter --> BenchBuilderAgent
    BenchBuilderAgent --> BenchmarkDraft
```

## Dependencies

- Internal: typed agent definitions, immutable production-support models,
  deterministic reporting, handoff contracts, and benchmark builders.
- Injected protocols: Airflow discovery and retry sources, cluster-health
  source, Resource Discovery, OMS and exact-log sources, and optional model
  runtime.
- External services: Airflow, Kubernetes/KEDA, Resource Discovery, and OMS
  through adapters outside this package.
- Composition: `PROD_SUPPORT_SOURCE=direct` uses provider adapters, `mcp` uses
  capability clients, `replay` uses captured benchmark evidence, and `empty`
  is the safe no-failure local mode. Replay and empty modes do not create OMS
  or Resource Discovery clients.
- Resource Discovery production composition prefers a unique API response and
  uses the maintained non-secret local client index when the API is empty or
  ambiguous.
- Persistent configuration: omission settings under
  `~/.prod_support/omissions.json`. New local configurations register D2P,
  MI3, Subscriber, Maintenance, Backfill, and CMM by default. Maintenance
  includes `log_cleanup` tasks such as `expire-logs-3`. All configured
  omissions stay hidden from Data Internal, Follow Up, and retry candidates.
- Optional durable memory: when the shared agent-memory PostgreSQL settings
  are configured, the workflow stores one confirmed, bounded diagnosis summary
  per exact failed task instance. Summaries contain task identity,
  classification, confidence, and evidence state only; raw logs, prompts,
  reports, and resource payloads are never stored.
- Side effects: investigations and benchmark construction are read-only.
  Approved FollowUp execution may clear only the exact validated task
  instances in its unchanged retry plan.
- Telemetry: shared OpenTelemetry API instrumentation and an SDK console
  exporter configured by the MCP composition root. W3C context may enter from
  MCP input; console JSON is written to stderr.

## Workflow

1. `Do prod support` and `Do prod support for yesterday` route through the
   `run_prod_support` MCP tool and shared workflow harness. Orchestrator
   resolves US and CA plus the prior operational day beginning at 05:00 UTC.
   The selected composition mode changes only capability transport; workflow
   policy and report rendering remain unchanged.
2. It invokes ClusterAgent and TriageManager concurrently when both are needed.
3. ClusterAgent reports health per requested region with observation time and
   evidence.
4. TriageManager receives every failure in one batch. It first classifies
   captured failure messages, then queries exact Airflow metadata and OMS where
   applicable. It fetches detailed task logs only for unresolved failures.
   Omitted jobs do not trigger Resource Discovery. Other client resolution
   passes the complete UUID from the DAG or task identifier and rejects
   report-only three-character prefixes. It uses unique API evidence or the
   authoritative local index;
   reporting shortens
   `Scotiabank - Data Validation` to `Scotiabank DV`.
5. Reporter receives completed findings and may refine only the Developer
   message. Data Internal and Follow Up remain the verbatim deterministic
   drafts, preserving region and client boundaries, underscores in job
   identifiers such as `active_deposit_accounts` without converting them to
   spaces or hyphens, concise multi-job rows without causes or periods,
   mandatory Follow Up actions, and omission filtering.
   The links section contains exactly the
   US and CA task-instance list URLs, bounded by greater-than-start and
   less-than-end `end_date` filters.
6. Orchestrator serves the Reporter output without rewriting it. The MCP
   response exposes `links`, `developer_message`, `data_internal_message`, and
   a direct-action `follow_up_message`. The user-facing response presents only
   `data_internal_message` as Slack-friendly mrkdwn; links, Developer, and
   Follow Up remain plain text. It uses no code fences or GitHub-style
   headings.
7. A developer follow-up executes exact eligible retries in one step and
   returns the original US and CA validation links for verification.
   Airflow capability MCP tools remain read-only and never expose retry
   execution.
8. If the request also asks to build a benchmark case, Orchestrator invokes
   BenchBuilderAgent after normal support. The MCP response keeps every normal
   production-support field and adds benchmark artifact metadata.
9. The MCP response includes the active trace and span IDs. Spans end after
    bounded result metadata is recorded.
10. When durable memory is enabled, the workflow records bounded summaries
    after reporting succeeds. Memory failure fails the run rather than silently
    returning an incomplete durable record.

Invalid dates, empty scopes, malformed handoffs, unsupported parallelism,
report-contract violations, and changed retry plans fail immediately.

## Benchmark behavior

The active suite is
`benchmarks/production_support/dates/09-27-26`. It measures named-agent
invocation, parent-child attribution, exact handoff inputs and outputs,
cardinality, dependency ordering, delegation boundaries, authoritative output,
production mutation safety, benchmark quality, and MCP output continuity.

The suite was created for September 27, 2026 and evaluates the September 26
operational day. It does not retrofit removed v1 runs to the current expected
behavior.

## Verification

Tests under `tests/unit/workspaces/data_engineering/agents/` cover prompt
docstrings, tool ownership, suite structure, workflow behavior, reporting,
retry safety, and benchmark construction. Integration and end-to-end tests
cover MCP output continuity, adapters, registration, and matrix execution.
The capability parity integration test exercises Airflow metadata, OMS
evidence, and Resource Discovery through direct and MCP adapters and requires
identical production-support outcomes.
Observability tests assert parent-child context, exception status, safe
attributes, and redaction.

Run `uv run python scripts/check.py` before completing a change.

## Change policy

Update this document when prompts, agent boundaries, tool ownership,
delegation, operational semantics, benchmark handoffs, or side-effect rules
change.
