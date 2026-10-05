CREATE SCHEMA IF NOT EXISTS lineage;

CREATE TABLE IF NOT EXISTS lineage.graphs (
    graph_id uuid PRIMARY KEY,
    repository text NOT NULL CHECK (btrim(repository) <> ''),
    commit_sha text NOT NULL
        CHECK (commit_sha ~ '^[0-9a-f]{40}$'),
    source_ref text NOT NULL CHECK (btrim(source_ref) <> ''),
    profile text NOT NULL CHECK (btrim(profile) <> ''),
    extractor_version text NOT NULL CHECK (btrim(extractor_version) <> ''),
    generated_at timestamptz NOT NULL,
    fingerprint text NOT NULL
        CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
    graph jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (repository, commit_sha, profile, extractor_version)
);

CREATE INDEX IF NOT EXISTS lineage_graph_history
    ON lineage.graphs (repository, profile, generated_at DESC);

CREATE TABLE IF NOT EXISTS lineage.nodes (
    graph_id uuid NOT NULL REFERENCES lineage.graphs(graph_id) ON DELETE CASCADE,
    node_id text NOT NULL CHECK (btrim(node_id) <> ''),
    kind text NOT NULL CHECK (kind IN ('dataset', 'job')),
    namespace text NOT NULL CHECK (btrim(namespace) <> ''),
    name text NOT NULL CHECK (btrim(name) <> ''),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL,
    PRIMARY KEY (graph_id, node_id)
);

CREATE INDEX IF NOT EXISTS lineage_node_search
    ON lineage.nodes (namespace, name);

CREATE INDEX IF NOT EXISTS lineage_node_kind
    ON lineage.nodes (kind, name);

CREATE TABLE IF NOT EXISTS lineage.edges (
    graph_id uuid NOT NULL REFERENCES lineage.graphs(graph_id) ON DELETE CASCADE,
    edge_id text NOT NULL CHECK (btrim(edge_id) <> ''),
    source_node_id text NOT NULL,
    target_node_id text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('consumes', 'depends_on', 'produces')),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL,
    PRIMARY KEY (graph_id, edge_id),
    FOREIGN KEY (graph_id, source_node_id)
        REFERENCES lineage.nodes(graph_id, node_id) ON DELETE CASCADE,
    FOREIGN KEY (graph_id, target_node_id)
        REFERENCES lineage.nodes(graph_id, node_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS lineage_edge_upstream
    ON lineage.edges (graph_id, target_node_id);

CREATE INDEX IF NOT EXISTS lineage_edge_downstream
    ON lineage.edges (graph_id, source_node_id);

CREATE TABLE IF NOT EXISTS lineage.graph_diffs (
    graph_id uuid PRIMARY KEY
        REFERENCES lineage.graphs(graph_id) ON DELETE CASCADE,
    previous_graph_id uuid REFERENCES lineage.graphs(graph_id),
    changed boolean NOT NULL,
    summary jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
