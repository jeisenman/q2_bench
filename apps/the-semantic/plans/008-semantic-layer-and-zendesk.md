# Semantic Layer and Zendesk integration

## Objective

Replace the Semantic Layer placeholder with Catalog and Graph views of the same
existing lineage source, plus read-only Zendesk Help Center browsing. Preserve
selected nodes and search across views. Retain source commits, meaning origin,
and coverage gaps. Do not create a competing semantic generator or MCP service.

## Sources and scope

Use qtwo_bench's existing Go lineage-service JSON API on loopback port 7420.
Catalog and directed neighborhoods derive from its one scoped /graph response;
node detail uses /node/{encoded identity}. The app accepts finite read operations
only. It does not enable definition writes, formal program loading, arbitrary
URLs, data execution or inference of missing edges.

Researcher now publishes paired bundle/graph v3 contracts. The previous sync
consumer accepts only v2 and rejects the current publication. Extend that
existing consumer with exact paired v2/v2 and v3/v3 acceptance, preserving
request-digest, exact coverage and provenance checks and rejecting mixed pairs.
Only synchronize and serve current source after the existing checks pass.

The generation records the request input as requests-zendesk-v2.1-final.jsonl,
not the old default requests.jsonl. A new explicit --requests override requires
--generation and selects that artifact before completeness/digest checks. The
selected file matches the manifest hash; no integrity check was relaxed.

The public Researcher database-backed MCP cannot currently start against the
documented local database. Docker is not running. The existing supported
published snapshot path removes that dependency for read-only lineage browsing;
it does not establish database health or runtime pipeline equivalence.

For Zendesk, use the existing September 2, 2026 export (396 articles, 3,404
chunks) through a trusted local snapshot pointer, alongside live public reads.
The pointer is var/zendesk-snapshot, outside tracked source. Data is not copied
or regenerated. Historical content remains explicitly dated.

The live public integration reads the PrecisionLender Help Center:
https://support.precisionlender.com . User scope clarification for support tickets
is pending. Public access exposed 26 articles at initial validation, including
support/SSO material; it is not the full authenticated Zendesk corpus. No ticket
API, authentication, private corpus access or snapshot ingestion is implied.
Do not infer lineage-to-article matches from title similarity.

## Boundaries and behavior

- Electron main process owns service connections; renderer uses finite preload IPC.
- Lineage service origin is a validated loopback origin, default port 7420.
- Help Center uses one fixed HTTPS host and locale; no credential extraction.
- Preserve TLS validation. Native Electron uses Chromium networking/system trust.
  Browser preview uses Node's system CA support where needed.
- Bound fetch time and bytes; validate returned shapes before rendering.
- Catalog and Graph share selection/query. Graph shows declared directed edges
  in a bounded neighborhood, with visible subset/truncation counts.
- Distinguish generated meaning from approved human definitions and retain
  unresolved coverage. Keep technical pins available without making opaque IDs
  the primary page headings.
- Article bodies become plain text; scripts, markup and remote resources are not
  executed. Retain article URL and update time. Public documentation is evidence
  of documented intent, not proof of source behavior or empirical effects.
- Missing services and empty results are explicit. Never substitute fake data or
  silently fall back to an old snapshot.

## Verification

Run qtwo semanticsync success/boundary/failure tests and repository quality checks.
Then validate dry-run, sync atomically, start a fresh existing lineage-service,
and check health/graph/node with current provenance. No cloud reads or writes.
Run The Semantic's quality command, finite-IPC and graph selection tests, Help
Center URL/schema/plain-text tests, then native Electron checks and visual review.
No model invocation, accepted experiment, ticket change or message is needed.

## Implementation evidence

Current pinned sync passed dry-run and atomic publication after explicit request
selection. The generation is e020475b-bc7b-40d7-9652-00935e2565fd.
Published source: 844 logical nodes and 1,428 edges. Existing typed projection
returns 126 jobs, 718 datasets and 3,730 columns, with 5,158 edges and two explicit
coverage findings. All 844 logical nodes have generated meaning; none has an
approved SME definition. Current source commits are retained.

Fresh existing lineage-service is running at http://127.0.0.1:7420 with
LINEAGE_SCOPE=all, Q2_MCP_DEBUG=1, and instance ID
the-semantic-source-v3-20261118. Health and graph reads passed. No write token is
configured. API users must retain the graph coverage limitations. The graph is
not a runtime DAG-equivalence or complete dependency certificate.

The generation has embedded Help Center URLs in generated text, not structured
article-support records. Preserve those texts; do not imply every generated
claim is independently supported or SME approved.

Both semanticsync package tests and the qtwo repository quality command passed.
The Semantic quality command passed: 32 Rust tests, 30 API tests, 24 desktop
tests and 5 runtime tests, plus format, lint, type checks, builds and the real SDK
fixture closure. Concurrent proposal support remains intact. Native Electron
validated both the existing saved-session/security path and the current lineage,
archive/public Help Center, plain text, trusted HTTPS and CSP path.

Browser QA passed catalog search, selection retained in Graph, typed meaning and
coverage display, dated snapshot article search/detail, and distinct live public
mode. A narrow-screen overflow was fixed by containing horizontal graph scrolling
and adding a visible hint. The final targeted visual check is recorded below.

Build warnings identify the helper dual ESM/CJS module-location branches and a
future Vite native-config-loader change. Both current preview and bundled native
paths passed. No warning was suppressed. No paid model call or cloud execution
was required.

A fresh rebuilt q2 lineage MCP process with Q2_MCP_DEBUG=1 exposed its existing
14 tools and returned an exact node from the current source graph through
explain_node. This was a read-only verification, not a new semantic MCP surface
or an rc tool-registration change. The process was closed after validation.

## Repeatable source setup

From /Users/jeisenman/ra/qtwo_bench, use the same explicit generation/request
selection for dry-run and publication:

```sh
go run ./cmd/agentbench semantic-sync --dry-run \
  --generation /Users/jeisenman/ra/researcher/runs/lineage/generations/737fdd39-dba5-5cd6-9e79-0977aba5cada-zendesk-v2.1-luna-medium-policy-ca-20261116 \
  --requests /Users/jeisenman/ra/researcher/runs/lineage/semantic/737fdd39-dba5-5cd6-9e79-0977aba5cada/requests-zendesk-v2.1-final.jsonl
```

After a passing dry-run, repeat without --dry-run. Then start the existing service:

```sh
Q2_MCP_DEBUG=1 LINEAGE_SCOPE=all \
  LINEAGE_GRAPH_PATH=/Users/jeisenman/ra/qtwo_bench/var/lineage/di-pipelines.json \
  go run ./cmd/lineage-service --listen 127.0.0.1:7420
```

This source service is independent of rc. It remains available after a normal
research chat exits, but rc does not install a system service or regenerate source
snapshots. Do not restart an unknown listener. A later generation requires a new
explicit source selection and the same validation, not a metadata-only version bump.

Targeted 390px browser recheck passed: page width and scroll width were both
390px; the graph region contained its 650px content in a 332px viewport. The
scroll hint was visible, and keyboard scrolling revealed the full target node.
The native app was not available to the screen-control surface; its actual
main/preload integration checks passed separately as described above.


Graph viewport update: Graph fills the page width and places selected-node details
below the canvas. Fit to view includes all displayed nodes. Zoom controls use
25% to 800% of Fit; drag or canvas arrow keys pan. Expand graph fills the app
viewport; Restore graph or Escape returns to page layout. Resize recalculates
Fit geometry. Catalog layout, directed edges, 40-node / 80-edge caps, selection,
source reads, and stale/error evidence are unchanged. Desktop behavior tests
cover fit bounds, zoom limits, expansion, selection, resize and listener disposal.

Catalog uses two independently scrollable panels with bounded heights. Selection
keeps the list scroll position; a new query resets it. Narrow screens stack the
bounded panels. Graph keeps its separate canvas and below-graph detail layout.
Definitions show supplied business context and readable labels. Commit hashes,
source paths, exact identifiers and machine descriptions remain available in
closed Technical evidence. No new business meaning is inferred by the renderer.
