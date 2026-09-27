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
`index.py` builds immutable indexes over authoritative, non-secret lookup
records by normalized client UUID and parsed client name. The parser applies
approved display conventions, including shortening
`Scotiabank - Data Validation` to `Scotiabank DV`, while retaining both the
original and parsed names as lookup keys.
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
- `adapters.resource_discovery`: production composition prefers a unique live
  API result and falls back to the repository's maintained non-secret JSON
  client index when the API result is empty or ambiguous. The lookup path can
  be overridden with `RESOURCE_DISCOVERY_CLIENT_LOOKUP`.
- External service: Resource Discovery API, when a production adapter is
  injected.
- Credentials: owned and validated by the external API adapter, never this
  package.
- Mutable storage: None. The packaged JSON index is read-only at runtime.

## Workflow

1. Validate the structured identifier or the request's `identifier` (or
   `identifier_kind`/`identifier_value`) attributes. The free-form prompt is
   never parsed for search values.
2. Call and await the injected source's read-only `lookup` method with the
   immutable `ResourceIdentifier`.
3. A production adapter accepts a unique API result. For an empty or ambiguous
   client result, it may query the authoritative local UUID/name index and
   preserve the original API cardinality if no indexed match exists.
4. Validate returned records, discard unknown fields, and order safe metadata
   by a stable key.
5. Classify the result as `not_found`, `unique`, or `ambiguous`.
6. Render only the fixed non-secret metadata fields. Preserve an explicit
   reviewed resend URL and `prod_support_ignore` marker for typed downstream
   consumers; never derive either value from a subdomain or environment.
7. Return the report, correlation ID, tool name `ResourceDiscovery`, and safe
   cardinality attributes.

Invalid identifiers, duplicate request attributes, invalid source records, and
source exceptions fail immediately. The workflow has no externally visible
side effects.

## Verification

Focused tests cover identifier validation, source failure propagation,
deterministic ordering, not-found/unique/ambiguous reports, secret-field
exclusion, parsed-name indexing, authoritative fallback behavior, maintained
UUID resolution, and `AgentResult` tool metadata. Repository formatting, lint,
typing, test, file-length, and documentation checks verify the package
boundaries.

## Change policy

Update this document when the identifier vocabulary, name parsing, local index
contract, fallback policy, allowlisted metadata, source protocol, report
contract, agent definition, failure behavior, or side-effect boundary changes.
