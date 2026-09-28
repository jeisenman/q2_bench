# Agent memory

Reviewed: 2026-09-28

Agent memory is a provider-neutral, tenant-scoped subsystem. Domain contracts
live in `src/agent_memory/`; PostgreSQL and local implementations live in
adapters. Agents receive an `AgentMemory` dependency explicitly.

## Storage model

The PostgreSQL migration is
`migrations/postgres/001_agent_memory.sql`. It creates:

- `memory.memories` for lifecycle, scope, content, optional vectors, and
  confidence;
- `memory.aliases` for typed canonical entity relationships;
- `memory.evidence` for append-only confirmations and rejections;
- tenant row-level security policies using transaction-local
  `app.tenant_id`.

Embeddings are optional. Exact aliases use the normalized-key index rather than
vector similarity. Future semantic memory can populate `embedding` and
`embedding_model` without changing the base record contract.

Apply the migration with an appropriately privileged PostgreSQL role:

```bash
psql "$AGENT_MEMORY_POSTGRES_DSN" \
  -f migrations/postgres/001_agent_memory.sql
```

The database must provide the `pgcrypto` and `vector` extensions.

## Runtime configuration

Durable memory is disabled when `AGENT_MEMORY_POSTGRES_DSN` is absent. When it
is present, these values are required:

```text
AGENT_MEMORY_POSTGRES_DSN
AGENT_MEMORY_TENANT_ID
AGENT_MEMORY_SCOPE_ID
```

`AGENT_MEMORY_SCOPE_TYPE` defaults to `organization` and accepts `user`,
`team`, or `organization`. `AGENT_MEMORY_ALIAS_CONFIRMATIONS` defaults to
three.

## Resource Discovery policy

Resource Discovery version two resolves requests in this order:

1. Exact authoritative local JSON identity.
2. Confirmed exact alias memory.
3. Unique acronym candidate requiring confirmation.
4. Live Resource Discovery API.

Memory stores only alias-to-canonical-client relationships. The canonical UUID
is dereferenced through the resource source on every resolved lookup, so memory
does not become a stale resource database.

The first `CNB` request may return a confirmation containing a `memory_id`.
Call the agent with scalar attributes `memory_id` and
`memory_outcome=confirmed` or `rejected`. Three confirmations promote the alias
to automatic resolution.

Raw prompts, outputs, resource payloads, and credentials are not persisted.
Memory reads and writes emit child OpenTelemetry spans.

## Production-support policy

Production support uses the same environment-driven memory composition with
the agent ID `production-support`. After a successful investigation and report,
it stores one confirmed summary for each exact failed task instance. The
summary is limited to region, DAG ID, task ID, diagnosis, confidence, and
evidence source/status. It never contains the task log, prompt, complete
report, client resource payload, or credentials.
