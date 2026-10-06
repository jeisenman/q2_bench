# Planning agents

## Purpose

This package defines provider-neutral agent contracts and deterministic planning
agents. Requests contain an objective and correlation ID; results contain a
stable plan and bounded metadata. Planning agents do not call providers or
mutate external systems.

## Architecture

[`contracts.go`](contracts.go) defines the public `Agent` interface.
[`planning.go`](planning.go) validates and renders immutable workflow steps.
[`scaffolds.go`](scaffolds.go) declares the KPO, ETL, data-finder,
data-creator, triage, and benchmark-builder agents. [`registry.go`](registry.go)
returns those definitions in deterministic order.

State is copied at construction and read concurrently without mutation.
`context.Context` carries cancellation and W3C-compatible trace context through
the public API. A concrete OpenTelemetry tracer is not instantiated in this
pure package; the calling composition root owns the root agent span. There are
no delegated subagents or tool spans because execution is plan-only.

## Dependencies

- Internal packages: [`../domain`](../domain) for request, result, definition,
  and tool contracts.
- Injected protocols: None.
- External services or SDKs: None.
- Runtime configuration: None.
- Telemetry: trace context is accepted through `context.Context`; exporters and
  root-span creation remain the composition root's responsibility.

## Workflow

1. Validate the request and immutable agent definition.
2. Render the objective and ordered workflow steps.
3. Return declared capability names and bounded execution metadata.

Invalid definitions and requests fail before output. No parallel work, network
access, delegation, or external side effects occur. The caller-owned invocation
span ends after `Run` returns.

## Verification

[`planning_test.go`](planning_test.go) verifies deterministic ordering,
validation, and capability metadata. `go test ./...` and the repository quality
command verify the package. The current composition does not include exported
span assertions; correlation IDs are preserved and prompts are not copied into
attributes.

## Change policy

Update this document when public contracts, scaffold steps, dependencies,
state ownership, side effects, or telemetry ownership changes.
