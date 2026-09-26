# Resource discovery agent

## Purpose

The resource discovery agent searches an injected async read-only source by one
structured identifier and reports non-secret client and resource metadata.
Inputs are `ResourceIdentifier` values or `AgentRequest` attributes; outputs are
`ResourceSearch` values and deterministic `AgentResult` reports. It never
infers a client, reads credentials, mutates a provider, or renders secret
values.

## Architecture

`agent.py` exposes `ResourceDiscoveryAgent` and the version-one
`AgentDefinition`. `models.py` defines immutable identifiers, allowlisted
metadata, and explicit cardinality statuses. `ports.py` contains the
`ResourceDiscoverySource` protocol for injected read-only providers. Provider
records are sanitized into the explicit metadata allowlist before reporting.
The allowlist includes reviewed resend URLs, routing provenance, and a boolean
production-support ignore marker; unknown keys, including secret fields, are
ignored.
`reporting.py` renders a fixed, deterministic non-secret field set, and
`__init__.py` defines the public API.

The agent is stateless after construction. Provider and network concerns remain
behind the source protocol; no concurrency, persistence, or production writes
occur in this package.

## Dependencies

- `domain`: shared `AgentDefinition`, `AgentRequest`, `AgentResult`, and
  `ToolDefinition` contracts.
- `ResourceDiscoverySource`: injected async provider boundary returning records
  that are sanitized into allowlisted metadata.
- External services, credentials, runtime configuration, and mutable storage:
  None.

## Workflow

1. Validate the structured identifier or the request's `identifier` (or
   `identifier_kind`/`identifier_value`) attributes. The free-form prompt is
   never parsed for search values.
2. Call and await the injected source's read-only `lookup` method with the
   immutable `ResourceIdentifier`.
3. Validate returned records, discard unknown fields, and order safe metadata
   by a stable key.
4. Classify the result as `not_found`, `unique`, or `ambiguous`.
5. Render only the fixed non-secret metadata fields. Preserve an explicit
   reviewed resend URL and `prod_support_ignore` marker for typed downstream
   consumers; never derive either value from a subdomain or environment.
6. Return the report, correlation ID, tool name `ResourceDiscovery`, and safe
   cardinality attributes.

Invalid identifiers, duplicate request attributes, invalid source records, and
source exceptions fail immediately. The workflow has no externally visible
side effects.

## Verification

Focused tests should cover identifier validation, source failure propagation,
deterministic ordering, not-found/unique/ambiguous reports, secret-field
exclusion, and `AgentResult` tool metadata. Repository formatting, lint,
typing, test, file-length, and documentation checks verify the package
boundaries.

## Change policy

Update this document when the identifier vocabulary, allowlisted metadata,
source protocol, report contract, agent definition, failure behavior, or
side-effect boundary changes.
