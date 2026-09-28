# Resource discovery agent

## Purpose

The resource discovery agent searches an injected async read-only source by one
structured identifier and reports non-secret client and resource metadata.
Inputs are `ResourceIdentifier` values or `AgentRequest` attributes; outputs are
`ResourceSearch` values and deterministic `AgentResult` reports. It never
infers a client, reads credentials, mutates a provider, or renders secret
values.

## Architecture

`agent.py` exposes `ResourceDiscoveryAgent` and versioned definitions.
`request.py` parses explicit attributes, bounded `find <client>` requests, and
memory confirmation commands. `models.py` defines immutable identifiers, allowlisted
metadata, and explicit cardinality statuses. `ports.py` contains the
resource, local-lookup, and acronym-candidate protocols. Provider
records are sanitized into the explicit metadata allowlist before reporting.
The allowlist includes reviewed resend URLs, routing provenance, and a boolean
production-support ignore marker; unknown keys, including secret fields, are
ignored.
`index.py` builds immutable indexes over authoritative, non-secret lookup
records by normalized client UUID and parsed client name. The parser applies
approved display conventions, including shortening
`Scotiabank - Data Validation` to `Scotiabank DV`, while retaining both the
original and parsed names as lookup keys.
`reporting.py` renders searches, alias confirmations, and feedback without raw
conversation content. `agent_memory.AgentMemory` owns exact alias policy and
depends on a storage port. `adapters.postgres` provides durable PostgreSQL
storage; `adapters.local` provides the deterministic test implementation.
`__init__.py` defines the public API.
The shared observability boundary emits `agent.resource-discovery.run`.

The agent holds no mutable state itself. Confirmed alias memory is scoped and
persisted through the injected memory service. Provider and database concerns
remain behind typed ports.

## Dependencies

- `domain`: shared `AgentDefinition`, `AgentRequest`, `AgentResult`, and
  `ToolDefinition` contracts.
- `ResourceDiscoverySource`: injected async provider boundary returning records
  that are sanitized into allowlisted metadata.
- `AgentMemory`: optional injected exact-alias service.
- `adapters.resource_discovery`: production composition short-circuits unique
  local JSON identities before calling the Resource Discovery API. The lookup
  path can be overridden with `RESOURCE_DISCOVERY_CLIENT_LOOKUP`.
- `adapters.postgres`: optional Psycopg-backed durable memory with pgvector,
  evidence history, and tenant row-level security.
- External service: Resource Discovery API, when a production adapter is
  injected.
- Credentials: owned and validated by the external API adapter, never this
  package.
- Mutable storage: optional PostgreSQL alias memories. Raw prompts, provider
  payloads, and resource copies are never persisted.
- OpenTelemetry API: bounded invocation and tool metadata. Exporters are owned
  by the application composition root.

## Workflow

1. Validate explicit identifier attributes or parse bounded
   `find|lookup|resolve|get|show <client>` wording. A `client_id` must remain a
   complete UUID.
2. For client names, query the authoritative local JSON index without network
   access. Return a unique exact match immediately.
3. Resolve a confirmed exact alias memory to its canonical UUID and dereference
   that UUID through the resource source.
4. If no alias exists, compare the mention with deterministic acronyms from the
   local canonical names. Persist a unique candidate as proposed memory and ask
   for confirmation.
5. Explicit confirmation evidence promotes an alias after the configured
   threshold; rejection deactivates it.
6. If local identity and memory cannot resolve the request, call the live
   Resource Discovery API.
7. Validate returned records, discard unknown fields, and order safe metadata
   by a stable key.
8. Classify the result as `not_found`, `unique`, or `ambiguous`.
9. Render only the fixed non-secret metadata fields. Preserve an explicit
   reviewed resend URL and `prod_support_ignore` marker for typed downstream
   consumers; never derive either value from a subdomain or environment.
10. Return the report, correlation ID, tool name `ResourceDiscovery`, and safe
   cardinality attributes.
11. End the delegated agent span; memory operations and async work retain its
   parent context.

Invalid identifiers, duplicate request attributes, invalid source records, and
source exceptions fail immediately. The workflow has no externally visible
side effects.

## Verification

Focused tests cover identifier validation, source failure propagation,
deterministic ordering, not-found/unique/ambiguous reports, secret-field
exclusion, JSON short-circuiting, acronym proposals, scoped confirmation,
automatic alias promotion, rejection, PostgreSQL schema policy, maintained UUID
resolution, and `AgentResult` tool metadata. Repository formatting, lint,
typing, test, file-length, and documentation checks verify the package
boundaries.
Shared observability tests verify W3C parentage, error recording, and exclusion
of arbitrary source and request payloads.

## Change policy

Update this document when identifiers, parsing, local indexing, memory scope or
promotion policy, PostgreSQL schema, allowlisted metadata, source protocols,
reporting, definitions, failures, or side-effect boundaries change.
