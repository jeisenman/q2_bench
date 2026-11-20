# Offline artifact reconciliation

This Go command reconciles an emitted one-pass dataset rollout. It makes no
network requests, model calls, semantic edits, retries, publication or approval.
It reads frozen inputs and emitted attempts/results without modifying them.
Default reporting requires every target to have a final result. An explicit
`--allow-incomplete` creates a point-in-time snapshot with pending targets and
unresolved attempts shown as held. It cannot prove that a dispatcher has stopped.

`models.go` defines the finite artifact contracts. `verify.go` checks pins and
source provenance. `reconcile.go` validates emitted result consistency and exact
three-key drafts only for results already marked successful. Failed raw outputs
are retained as links and hashes; they are never reconsidered for acceptance.
`citations.go` checks URL membership and reported article/chunk identities.
`validation_chain.go` checks any externally emitted artifact-only correction
against its preserved initial result, raw output, final draft and explicit
zero-additional-model-call/no-definition-edit assertions. The reporter does not
repeat that correction or reconsider a result still marked failed.
`render.go` writes a new report directory with complete JSON accounting and
Markdown indexes of at most 80 targets per file.

All definitions remain offline machine drafts. Citation mapping proves URL
membership in supplied evidence, not per-claim article support. Hash checks do
not establish semantic accuracy, runtime behavior, completeness or SME approval.
Use synthetic focused Go tests. Do not run the final report while dispatch is
active. Keep every source and Markdown file below 400 lines.
