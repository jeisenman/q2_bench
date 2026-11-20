# Desktop

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

Semantic Layer navigation stays inside `semantic-view.ts`: Lineage, Zendesk,
Definitions, Repositories, and Research are the five peer knowledge bases.
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
Only observed operation names, states and timings are shown. Completed assistant
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
