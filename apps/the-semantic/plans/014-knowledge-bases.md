# Five Semantic Layer knowledge bases

The approved sidebar replaces the Semantic Layer's eight view tabs with five peer
knowledge bases in this order: Lineage, Zendesk, Definitions, Repositories, and
Research. Rows use compact message-list spacing and the existing journal
palette. CSS stays under the Semantic Layer mount; narrow layouts stack the
sidebar above the content. The original global Research ledger remains intact.

Lineage keeps Catalog and Graph as a local switch. Both retain the same scoped
source graph, query, selected identity, bounded neighborhood and viewport controls.
Catalog uses a readable Name / Kind / System or scope table. Exact-node detail
and the existing guarded SME document editor appear below the selected table.
Generated meaning, upstream SME text, local drafts, source evidence, coverage
limits, unavailable sources and stale snapshots retain their existing boundaries.

No wiki connection is planned. Definitions uses actual supplied SME text.
Repositories uses actual source references; optional
source search is off and disconnected. Component namespaces stay source metadata.
Zendesk retains the dated export and explicitly selected public Help Center reads.
No transport, CSP, iframe isolation, service or MCP surface changes are required.

Research reads at most 100 actual records through the existing list operation,
keeps FINISHED records only, and sorts by creation date newest first. The host
receives the original research ID and opens that exact record through the existing
editorial Research detail path. Failed or pending records are not completed work.
An unavailable reader or absent callback stays explicit. Disposed reads and
callbacks cannot update the replacement view. Navigation does not invoke models.

Verification covers the five-base order and selection, table fields and detail
placement, preserved query/selection across Catalog and Graph, SME editor access,
missing source states, newest-first completed research and exact-ID callbacks,
and stale/disposed reads. The native current-source smoke uses the actual preload,
lineage table, Graph, and both Zendesk modes. Shared Research layout and Codex
styles are outside this change. Run desktop tests, typecheck and build, then the
repository quality gate. Rebuild/relaunch the desktop to use the changed renderer;
no MCP process implementation is changed.

## Validation

The full `node scripts/check.mjs` gate passed, including 103 API tests,
desktop/runtime checks, builds, and the fixture CLI/SDK closure. Native Electron
isolation and current-source checks passed: 3,082 lineage nodes, 3,726 edges,
five unresolved findings, 396 snapshot articles, and 26 public articles.
These counts describe the checked source scope, not complete lineage coverage.
Hash comparisons confirmed that the Research ledger renderer, shared stylesheet,
and Codex view/sidebar styles stayed unchanged. The preview serves the new source.
Browser visual inspection was unavailable because its connection failed.

Pages removal: the focused semantic tests (four cases), desktop typecheck,
workspace tests and build passed. The full repository check stopped at the
unchanged Rust chat test
`termination_closes_session_as_interrupted_and_waits_for_native_child`, which
failed its expected PID-file assertion. No Rust or chat source changed.
