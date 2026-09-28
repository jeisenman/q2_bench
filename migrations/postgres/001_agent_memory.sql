CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS memory;

CREATE TABLE IF NOT EXISTS memory.memories (
    memory_id uuid PRIMARY KEY,
    agent_id text NOT NULL CHECK (btrim(agent_id) <> ''),
    tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
    scope_type text NOT NULL
        CHECK (scope_type IN ('user', 'team', 'organization')),
    scope_id text NOT NULL CHECK (btrim(scope_id) <> ''),
    kind text NOT NULL
        CHECK (kind IN ('alias', 'fact', 'preference', 'summary')),
    memory_key text NOT NULL CHECK (btrim(memory_key) <> ''),
    normalized_key text NOT NULL CHECK (btrim(normalized_key) <> ''),
    content text NOT NULL CHECK (btrim(content) <> ''),
    status text NOT NULL
        CHECK (status IN ('proposed', 'confirmed', 'rejected', 'superseded')),
    confidence double precision NOT NULL DEFAULT 0
        CHECK (confidence >= 0 AND confidence <= 1),
    evidence_count integer NOT NULL DEFAULT 0 CHECK (evidence_count >= 0),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    embedding vector,
    embedding_model text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (memory_id, tenant_id),
    CHECK (embedding IS NULL OR btrim(embedding_model) <> '')
);

CREATE UNIQUE INDEX IF NOT EXISTS active_memory_key
    ON memory.memories (
        agent_id,
        tenant_id,
        scope_type,
        scope_id,
        kind,
        normalized_key
    )
    WHERE status IN ('proposed', 'confirmed');

CREATE INDEX IF NOT EXISTS memory_exact_lookup
    ON memory.memories (
        tenant_id,
        agent_id,
        scope_type,
        scope_id,
        kind,
        normalized_key
    )
    WHERE status IN ('proposed', 'confirmed');

CREATE TABLE IF NOT EXISTS memory.aliases (
    memory_id uuid PRIMARY KEY,
    tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
    canonical_entity_type text NOT NULL
        CHECK (btrim(canonical_entity_type) <> ''),
    canonical_entity_id text NOT NULL
        CHECK (btrim(canonical_entity_id) <> ''),
    canonical_name text NOT NULL CHECK (btrim(canonical_name) <> ''),
    FOREIGN KEY (memory_id, tenant_id)
        REFERENCES memory.memories(memory_id, tenant_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS alias_canonical_entity
    ON memory.aliases (canonical_entity_type, canonical_entity_id);

CREATE TABLE IF NOT EXISTS memory.evidence (
    evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id uuid NOT NULL,
    tenant_id text NOT NULL CHECK (btrim(tenant_id) <> ''),
    outcome text NOT NULL CHECK (outcome IN ('confirmed', 'rejected')),
    correlation_id text NOT NULL CHECK (btrim(correlation_id) <> ''),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (memory_id, correlation_id),
    FOREIGN KEY (memory_id, tenant_id)
        REFERENCES memory.memories(memory_id, tenant_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS memory_evidence_history
    ON memory.evidence (memory_id, created_at);

ALTER TABLE memory.memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory.memories FORCE ROW LEVEL SECURITY;
ALTER TABLE memory.aliases ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory.aliases FORCE ROW LEVEL SECURITY;
ALTER TABLE memory.evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory.evidence FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_memories ON memory.memories;
CREATE POLICY tenant_memories ON memory.memories
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS tenant_aliases ON memory.aliases;
CREATE POLICY tenant_aliases ON memory.aliases
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS tenant_evidence ON memory.evidence;
CREATE POLICY tenant_evidence ON memory.evidence
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
