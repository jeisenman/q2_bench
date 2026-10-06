# Resource Discovery agent

## Purpose

This agent resolves client and resource identifiers into allowlisted,
non-secret metadata. It supports local identity lookup, provider batches, and
explicitly confirmed alias memory. It never infers an ambiguous client or
mutates provider resources.

## Architecture

[`models.go`](models.go) defines identifiers, safe metadata, and cardinality.
[`request.go`](request.go) parses structured requests and memory feedback.
[`index.go`](index.go) owns deterministic identity indexing.
[`agent.go`](agent.go) coordinates local, memory, batch, and provider tiers.
[`reporting.go`](reporting.go) renders stable output.

The agent itself is stateless. Alias state belongs to
[`../../agentmemory`](../../agentmemory). Batch provider reads are issued once
when supported; fallback reads are sequential to preserve order.
`context.Context` carries cancellation and W3C-compatible trace context across
memory and adapter boundaries. The composition root owns the root agent span,
and adapters own child operation spans.

## Dependencies

- Internal packages: [`../../domain`](../../domain) and
  [`../../agentmemory`](../../agentmemory).
- Injected protocols: `Source`, optional `BatchSource`,
  `LocalLookupSource`, and `AliasCandidateSource`.
- External services or SDKs: Resource Discovery through an adapter.
- Runtime configuration: optional local identity data and alias-memory store.
- Telemetry: caller-owned root span; memory and provider implementations own
  child spans and exporters.

## Workflow

1. Validate the request and parse an explicit identifier or feedback action.
2. Apply feedback to the scoped memory store when requested.
3. For client names, attempt a unique local match.
4. Resolve confirmed memory or propose one unique alias candidate.
5. Query the provider only when earlier tiers do not resolve the request.
6. Sanitize, sort, classify, and render the result.

Batch requests validate all identifiers before the provider call. Invalid
metadata, ambiguity, memory conflicts, and provider failures stop immediately.
Alias evidence is the only mutation and is limited to the injected memory
store. Trace context is propagated to every invoked dependency.

## Verification

[`resource_discovery_test.go`](resource_discovery_test.go) covers identifier
validation, ordering, batching, local resolution, confirmation, rejection, and
safe rendering. Adapter tests cover transport behavior. Correlation IDs are
preserved; unknown provider fields and secret values are discarded before
reporting.

## Change policy

Update this document when lookup precedence, metadata allowlists, memory
policy, batching, dependencies, side effects, or telemetry ownership changes.
