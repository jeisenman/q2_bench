# Research refinement chat example

Start research detail with step `00 Chat thread`, before `01 Question`. Provide
an Open chat thread link to a read-only dialog and a separate Expand chat button
for initially collapsed inline messages. The static conversation refines a loan scenario modelling and
realized ROE question. Label the content as an illustrative fixture rather than
the originating conversation. The user explicitly requested a plausible sample
because existing research records do not retain a source-chat reference.

Keep the example in a presentation-only module. Reuse the journal's chat styles.
Do not change research records, persistent contracts, transports, or services.
Check section navigation, visible step order, fixture labels, and lack of input
controls. Run the desktop tests, typecheck, build, and repository quality gates.

Validation: Rust formatting, Clippy and tests passed; API lint, formatting and
103 API tests passed. Desktop typecheck, all desktop/runtime tests, builds and
the fixture CLI-to-API closure passed after correcting a test element type.
The qtwo_bench quality command with `--check-format` also passed. An Electron
capture verified the initial footer sample. The user then requested step 0 in
place of that footer; validation for the revised placement follows below.

Step 0 validation: the updated fixture test, all 65 desktop tests, all five
runtime tests, typechecks and builds passed. The qtwo_bench quality command
with `--check-format` passed again. Section links retain the existing Question
through Graphs targets and add `#stage-chat` as the first of six links.
Live-preview Electron inspection confirmed the six links, visible chat before
Question, six messages, and absence of the previous footer link.

The revised controls passed focused tests, all desktop/runtime tests, typechecks
and builds. Live-preview Electron inspection verified collapsed-by-default
messages, independent expand/collapse, dialog opening with six labelled fixture
messages, and Close. The separate qtwo_bench check failed in the unchanged
`TestToolCacheMiddlewareCachesReadOnlyToolsOnly` test (two read calls, expected
one); no Go or cache code is changed by this UI work.
