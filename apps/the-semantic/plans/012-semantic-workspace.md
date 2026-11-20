# Semantic Layer workspace

## Objective and scope

Extend only the Semantic Layer tab within the existing editorial application.
Retain the masthead, main navigation, and all other tabs. Cover repositories,
RA/Engine/DI-pipelines components, data lineage, Zendesk articles, definitions,
notes, and a newest-first research archive.

## Boundaries

- Reuse validated lineage and Help Center readers. Keep selection, queries,
  directed edge limits, stale states, and source evidence intact.
- Keep repository source search optional and explicitly disconnected until a
  bounded source-search interface exists. Never imply that a checkout was read.
- Show only supplied SME meaning as a source definition. Local SME drafts retain
  the existing editor and do not become upstream approval.
- Notes are a memory-only preview. Do not persist private text in browser storage.
- Read research through existing finite operations. Keep missing notebook,
  visual, and artifact capabilities explicit. Do not invent research evidence.
- Add no service, transport permission, model call, or execution operation.
- Scope new styles to the Semantic Layer. Preserve existing unsaved edits.

## Regression checks

The pre-change desktop baseline passed all 39 tests. Run the full application
quality command and new semantic workspace tests after the change. Check actual
Electron reads against available local services. Confirm that files for other
tabs and shared transport contracts have no changes from this task.

Browser inspection depends on the computer-use connection. A failed connection
does not establish visual correctness; report that verification limit.

## Verification evidence

- Desktop: 43 tests passed, including the 39 pre-change tests; TypeScript check
  and desktop build passed. Runtime: five tests passed. API: 59 tests passed,
  with one existing SQLAlchemy deprecation warning. Ruff checks passed.
- Native Electron isolation/CSS/CSP checks passed. Native semantic reads passed
  with the existing trusted Zendesk snapshot configured for that command only:
  3,082 lineage nodes, 3,726 edges, five unresolved findings, 396 retained
  articles, and 26 public articles. Counts describe this read, not full coverage.
- The default snapshot path was absent in this checkout. The first semantic
  native check reported that error; it did not substitute sample content. The
  configured check reused the existing snapshot pointer without changing it.
- The real CLI/SDK fixture closure passed. The full quality command stopped at
  two unchanged Rust runtime-selection tests (provider timeout / failed output
  status). Rust formatting and clippy passed. No Rust code was changed.
- The qtwo quality command passed. No qtwo code or MCP process was changed.
- Hash comparison confirmed other tab behavior and existing user edits remained
  unchanged. The renderer loads the scoped stylesheet as a module import.
- Browser visual inspection was blocked by the computer-use connection reporting
  `native pipe closed before response`; no visual regression claim is made.

## Preview stylesheet correction

The active Vite preview returned HTTP 500 for a nested CSS `@import`, although
the target stylesheet existed and the production build passed. Load the scoped
stylesheet from the renderer entry beside the existing stylesheet imports.
The running preview then returned HTTP 200 for both stylesheets and the renderer
module, which referenced the resolved Semantic Layer stylesheet path. No style
rules or navigation behavior changed in this correction.

## Inline SME editing

Place Edit and Version history in the selected item's upper-right header.
Hover/focus identifies the SME definition; active editing highlights that area
and places its form before generated context. Cancel and confirmed Save restore
the reading view and button focus. Failed saves retain the form and highlight.
Other document editors keep their existing controls unless an explicit action
host and editable region are supplied. Tests cover placement, focus, Cancel,
save failure, successful Save, disposal, and the existing shared editor behavior.
