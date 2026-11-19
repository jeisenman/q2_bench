# The Semantic desktop

From the repository root, run `npm install`, then `npm run desktop`. Start the
research API on 127.0.0.1:5056 first. Register an agent and run an accepted plan
with the CLI, then refresh the Research ledger or Agent Catalog.

For visible browser QA, run `npm run preview --workspace @the-semantic/desktop`
and open http://127.0.0.1:4175. This development preview reads the same live API
through the Vite loopback proxy. It is marked Browser preview and exposes only the finite local operations.
The production build requires the finite Electron preload bridge.

Research supports search, UTC date order, exact-record details and a five-stage
question/hypothesis/experiment/runs/graphs chain. The sandboxed run summary shows
actual retained metrics with units and output.

After a production build, run `npm run test:native --workspace
@the-semantic/desktop` from the root for the explicit Electron smoke check.
It needs the local API and runs the actual bundled main and preload. It checks
finite live reads, rejection of unsupported operations, renderer isolation and
blocked renderer network access. It does not run a model.

Research Sessions shows saved native Codex sessions, including ACTIVE sessions
created before the first prompt. Select a session and use Refresh sessions to
read new messages or terminal status. Counts are snapshots, with the read time
shown. Failed reads preserve a clearly marked stale snapshot. No model call or
agent delegation runs from this view.

`researcher-codex chat` opens the exact session through `--research-session <id>`.
A second launch focuses the existing app and selects the new session. For native
routing verification, append `-- --research-session <saved-id>` to the explicit
`test:native` command. The API must contain that saved session.

Draft proposals can be listed, searched, read and saved in the Proposals tab. Saving uses a finite validated local API mutation and does not accept or run an experiment. The browser preview permits this same fixed route. An uncertain save can be retried with the same idempotency key until the form changes.


Semantic Layer connects to the existing independent Go lineage service. Its
Catalog and Graph share search and exact-node selection. The graph displays a
directed one-hop subset capped at 40 nodes and 80 declared edges, with explicit
truncation counts. Node details separate SME definitions, generated meaning,
source pins and unresolved coverage. An unavailable source is explicit; a failed
refresh marks previously read data stale. There is no staged snapshot fallback.

SEMANTIC_LINEAGE_URL defaults to http://127.0.0.1:7420 and accepts only a trusted
HTTP loopback origin. The source must serve the validated current lineage. The
desktop exposes only graph and exact-node reads, bounded to 32 MB and 15 seconds.

Help Center has two independent sources: the dated Zendesk export (default) and
the live public Help Center. SEMANTIC_ZENDESK_SNAPSHOT selects a trusted host
directory; otherwise the app uses var/zendesk-snapshot under this worktree.
The UI shows export provenance, source article dates and result limits. Search
is preserved when switching sources. It does not infer article-to-node mappings
or treat knowledge as approved SME definitions. HTML becomes inert plain text
through parse5; source links open only validated public PrecisionLender article
URLs in the external browser. No tickets, authentication or Zendesk writes exist.

Electron uses net.fetch with normal system trust for public HTTPS. The preview
script starts Node with --use-system-ca for the same trusted corporate root
certificates. Never disable TLS verification.

After building, run npm run test:semantic-native --workspace
@the-semantic/desktop for explicit read-only integration with the current lineage
service, configured snapshot and live public articles. This check makes no model
call. Unit tests use clearly synthetic source fixtures.
