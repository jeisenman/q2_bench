# Versioned document editing

Objective: all four artifact types support explicit Edit, Save, Cancel, and
read-only version history. Save changes the persisted document and retains the
original source plus each saved version. No save starts research.

The desktop uses one finite validated document bridge. The research API owns
validation, optimistic concurrency, idempotency, immutable MLflow snapshots,
and publication. Proposal and terminal research reads project the latest saved
content. Research execution evidence is retained. Agent saves add an immutable
ID/version; existing research pins are unchanged. SME edits persist local drafts
with source commit metadata; upstream approved definitions stay separate.

Checks cover reload persistence, version history, stale saves, duplicate requests,
failed publication, invalid content, retained form text, Cancel, safe rendering,
and navigation guards. Existing runtime, Rust, API, desktop and security checks
remain required. Restart the changed API and validate a fresh MCP child. Visual
checks use Edit and Cancel without changing an existing user document.

Bounds: at most 100 retained versions including the original. One API process
serializes writes. Cross-service transactions and upstream SME publication are
outside this feature. Missing storage is an explicit error.
