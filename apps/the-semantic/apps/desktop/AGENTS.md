# Desktop

`research-chat-fixture.ts` presents `00 Chat thread` before Question on research
detail pages. Its link opens a read-only dialog; a separate button expands the
initially collapsed inline messages. It is a labelled example, not source
provenance. It has no transport, persistence or model operations.

Electron main owns finite fixed-origin research reads and document saves. Preload exposes only
`semantic.read`, validated `proposals.save`, and `documents.save` mutations; it validates requests and responses. Renderer has no Node or
production network capability. Browser preview is explicit Vite development
mode on 127.0.0.1:4175 and uses its finite local proxy.

Research and Agent Catalog render live validated service evidence. Plugin host
loads the packaged run-summary manifest only and transfers selected evidence
through a MessageChannel. Iframes have allow-scripts only; no same-origin,
preload, Node, generic IPC or direct API access. Close old ports on view changes.

Build with npm run build; test with npm test. Keep service strings in textContent
and use explicit unavailable states. Never create fake live data.

Research Sessions reads normalized native Codex records through sessions.list/get.
It uses manual snapshots with explicit timestamps and stale/error states; it has
no timers or model calls. Session view disposal invalidates pending reads. Session
schemas reject private payload fields, invalid counts and tool text. A display
filter also removes credential-like values before textContent. Main accepts only
the bounded --research-session ID flag. Single-instance launches focus/reload the
existing window with validated Electron additionalData, which avoids reordered
second-instance argv; closing a window permits reopening.


Semantic Layer reads graph/node only from the trusted loopback lineage origin.
lineage-contracts validates full typed source shapes and nested wire IDs. The
renderer uses original bounded SVG, retaining only declared directed edges.
Catalog/Graph share query and selection. Graph fills the page width and places
node detail below its bounded, fitted SVG canvas. lineage-viewport owns fit,
bounded zoom, pan, resize and expansion controls; dispose its listeners on render.
Catalog uses a bounded table with selected-node details below and retains
list scroll position during selection. Stale/offline state must remain explicit.
Do not import qtwo or Researcher code, invent edges or create a semantic service.
Main definitions show readable labels and supplied business context. Keep raw
identifiers, commits and machine descriptions in closed Technical evidence.
Never generate new business meaning while formatting source labels.

Knowledge sources remain separate: configured read-only Zendesk export and fixed
public HTTPS Help Center. knowledge-snapshot validates the bounded manifest and
corpus; help-client parses HTML inertly with parse5. Main uses Electron net.fetch
for system trust; preview uses Node --use-system-ca. Never disable certificate
validation. No renderer-supplied origins, paths, credentials or ticket operations.
Only validated fixed-host public article URLs may open externally; all child
BrowserWindows remain denied. Knowledge is not an SME definition or an inferred
article/lineage mapping. Preserve queries when switching knowledge sources.

Codex is a persisted live chat in `codex-view.ts`. Each explicit message invokes
one bounded installed-Codex turn through the finite `semantic:chat` IPC and API.
`chats.ts` validates messages and tool attachments. `chat-animation.ts` animates
completed text and releases timers on disposal; it does not claim live token
streaming. No model fallback, automatic send retry, or renderer process bridge.
The server decides whether to prepare a draft; client keywords never fabricate
an attachment. `proposal_prepare` returns a saved unaccepted proposal.

`proposal-modal.ts` opens that exact document through existing versioned reads
and saves. The pen highlights all fields without text focus. Save/Cancel,
optimistic versions, stable retry keys, guarded closure and inert history retain
source evidence. Dispose listeners and dialogs with the mounted chat. Chat drafts
and saved proposals never authorize research execution. Native tests use isolated
API fixtures and the actual preload, without a paid model call.

`document-editor.ts` supplies Edit, Save, Cancel and read-only version history for
proposal, research, agent and local SME documents. Forms retain text and the
idempotency key after uncertain saves. Optimistic version checks reject stale
writes. Dirty forms guard navigation; dispose their listeners with the view.
Research edits preserve original execution evidence. Agent edits create a new
immutable version. SME drafts are MLflow documents, separate from upstream
approved definitions; never label a local edit as upstream approval.

Document fields share `edit-box.ts` and `edit-box.css`. Bind displayed content
with `fieldTargets` for in-place editing. Keep targets stable until disposal.
See `../../docs/edit-boxes.md` for the design and behavior standard.

Semantic Layer navigation stays inside `semantic-view.ts`: Lineage, Zendesk,
Definitions, Repositories, Research, and PL-App Behavior are the six peer knowledge bases.
The default view is an editorial index; each row opens one full-width base.
All knowledge bases returns to the index and preserves source queries, selection
and cached lineage. The index makes no source reads. Only opening Lineage,
Definitions or Repositories loads a missing graph. Back disposes child views and
invalidates pending reads. Keep compact child row styles within semantic-workspace.
Lineage owns the Catalog/Graph switch. `semantic-sections.ts` owns repository
references and supplied SME definition links. No wiki connection is configured.
Repository source search is optional, off and disconnected. Component namespaces
remain source evidence, not another knowledge base.
`semantic-archive.ts` uses the finite research list read, filters FINISHED records,
and sorts newest first. Its injected exact-ID callback opens the original global
editorial Research detail in `renderer.ts`; it never executes a model or duplicates
the research renderer. Disposal invalidates pending reads and row callbacks.
`semantic-workspace.css` is scoped to the mounted Semantic Layer class, which is
removed on disposal. Shared navigation, transports, and other tab styles stay
outside these modules.

`chat-activity.ts` renders public operation metadata and polls the finite
`chats.activity` read every 750 ms while a submitted turn is pending. Polls
stop on completion, failure, deadline, or disposal; they never submit turns.
Only observed operation names and states are shown. Retained timings stay internal. Completed assistant
activity persists with the chat; legacy messages remain readable. Private
reasoning, arguments and provider payloads are excluded by strict schemas.

`chat-sidebar.ts` owns saved-chat navigation and local title filtering. It reuses
existing chat reads and creates no model requests. The selected chat uses
aria-current; pending turns disable navigation. The view protects unsent text
before a switch. The two-column layout stacks at narrow widths.

Message-style sidebar rows use topic initials and saved UTC dates. Previews come
only from chat records already loaded in this view; unopened records show saved
message counts. Refresh clears cached previews. No background history fetches
or fabricated snippets support this styling.

Gherkin reads only tracked regular *.feature blobs from a trusted local Git
checkout, through finite list/search/feature operations. The host alone selects
SEMANTIC_GHERKIN_ROOT (default ~/ra/pl-application). A page and its feature details
retain the exact immutable commit; refresh explicitly reads current HEAD. Literal
case-insensitive search, bounded pages, byte/time limits and unavailable states
stay explicit. Render source with textContent, retaining tags, indentation,
Background, Scenario Outline and Examples. Do not execute specs, invoke models,
or infer test results, business meaning or lineage connections. Dispose pending
view reads and callbacks. Preview has only canonical GET routes.

`chat-display.ts` projects text for chat headings, Markdown, tool details,
previews and animations. It hides internal execution references and retained
metrics. Historical records retain their original text internally; displayed
text uses the same projection. Source commits and paths remain source evidence.

`chat-markdown.ts` creates inert DOM for supported Markdown, with no HTML, remote
assets or executable links. `transcript-view.ts` renders immutable imported
public chat evidence through finite transcripts.list/get reads. Preserve source
order and text; every tool sequence starts collapsed. Arguments and outputs are
never executable operations. Historical records have no composer/model action.
Their explicit proposal link opens the current version in the shared editor.

Gherkin search advertises keyword and vector modes. Keyword uses the committed
Git reader; vector is disabled and must fail before source, filesystem, embedding
or provider work. The capabilities operation needs no checkout. Keep the disabled
Vector option visible in the search control. This feature adds no database or
vector index and never writes MLflow's SQLite backend directly.

The Gherkin workspace keeps the shell's PL-App Behavior heading as the only
knowledge-base title. Show committed feature rows in a bounded scroll region,
mark the selected row accessibly, and place the literal source detail below the
list. New searches clear selection. Scope its CSS beneath `.semantic-workspace`
and `.gherkin-workspace`; keep long paths and source usable at narrow widths.

Gherkin uses a master/detail layout: results and pagination stay together, with
selected source alongside on wide screens. Narrow selection reveals the detail
region. Rows identify the controlled region; its busy state covers exact reads.
`gherkin-detail.ts` adds a bounded literal English heading index, skipping
quoted docstrings. It is a display aid, not a Gherkin parser or interpretation.
The complete source text, including BOM, comments and whitespace, stays intact.
