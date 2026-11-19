# Deterministic Zendesk rollout preparation

This Go command reads frozen local lineage, published request/response contracts,
the pinned prompt, and the complete authorized Zendesk corpus. It makes no network
requests, model calls, publication, or source changes. The command validates all
inputs before writing a new preparation directory. Existing output
directories are rejected.

`identity.go` validates exact dataset identities and semantic provenance.
`corpus.go` validates article/chunk integrity and corpus pins. `retrieval.go`
selects bounded full-text evidence with deterministic lexical ranking.
`cleanup.go` records exact audit-only text edits and rejects ambiguous prose.
`caller_policy.go` implements the explicit `single-luna-pass` exception: retain
the complete original definition on ambiguous cleanup and mark it for the same
single model pass. The default conservative policy still blocks. The versioned,
hash-pinned policy is separate from the unchanged base prompt 2.0.0.
`context_projection.go` keeps the complete target and request in pinned review
artifacts, retains exact codeContext and targetNode, and supplies direct neighbor
identities with explicit references to omitted non-target inventories.
`capacity.go` validates the pinned local model catalog metadata and the approved
524288-byte/128000-estimated-token input budgets, including harness/output reserves.
The investigation-owned sibling `contract` package contains the stdlib-only
offline HTTP DTO snapshot. Preparation has no dependency on shared lineage
foundation packages. Its pinned attribution and wire compatibility tests belong
to that package. `target_parity_test.go` provides an explicit read-only comparison
of all 553 target bytes against a frozen run; it never invokes preparation.
`prepare.go` assembles per-target inputs and a hash manifest. `main.go` exposes
explicit file flags. Tests use synthetic local data only.

Keep each source below 400 lines. Preserve original source bytes and hashes in
the generated run. Reader-facing definitions contain no preparation manifests.
Never invoke this command on production inputs before the caller reviews the
audit cleanup contract. No automatic retry or model loop belongs here.
