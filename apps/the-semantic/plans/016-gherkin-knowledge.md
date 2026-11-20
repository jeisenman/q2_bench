# Gherkin knowledge base

Show `PL-App Behavior` after the five existing Semantic Layer bases. Keep its query and
source evidence independent of Lineage, Zendesk, Definitions, Repositories and
Research. Use the existing finite read bridge and a matching Vite preview route.
No model execution, semantic service, source execution or inferred links belong
in this feature.

The host selects ~/ra/pl-application or the absolute SEMANTIC_GHERKIN_ROOT
checkout. Resolve HEAD once for an initial list/search and retain its immutable
40-character commit for pagination and feature detail. Never replace an absent
commit with HEAD. Read tracked regular *.feature blobs through bounded Git
commands; exclude uncommitted files and symlinks. Search literal text without
case sensitivity. Preserve the full source, tags, Background, Scenario Outline,
Examples, repository, relative path and commit. Render source as inert text.

Bound each page to 25, inventory to 10000 features, inventory/search output to
8 MB, feature bytes to 1 MB, and each Git command to 10 seconds. Strict renderer
contracts reject roots, origins, traversal, unpinned detail and unknown preview
parameters. Failed or oversized reads show an unavailable state. Disposal blocks
late reads and callbacks. Refresh and a new search explicitly read current HEAD.

Regression checks cover source listing/search, no matches, pinned source after
HEAD changes, paging, absent repositories/commits/files, oversized source, strict
contracts, inert verbatim display, source identity mismatches, disposal, six-base
order and retained sibling-base queries. Run desktop tests, typecheck and build.
Root repository checks and runtime lifecycle verification remain with the parent
task. This change adds no MCP server operation.

## Validation

Desktop type checks, all 68 desktop tests, and the production build passed.
A fresh native Electron process passed the actual main/preload check against
334 committed application features at
`5af19e313f0012911d695abb6cf1690650a24874`. It checked six-base navigation,
literal content search, exact feature detail, and renderer isolation. The source
reader returned five matches for `rate lock`. These are specification reads,
not scenario execution results. The configured MCP containers were rebuilt and
recreated; both were healthy and production support reported the production
source with debug enabled.

## Approved view implementation

The approved preview is implemented in the live `PL-App Behavior` view. Compact
rows show the feature name and repository-relative path. Selection identifies
the current row and opens its original Gherkin beneath the results, with the
repository, source commit, and path. Result and source areas remain bounded for
large pages and files. Search and pagination use the complete configured source;
the preview's captured sample is not application data. Styling is confined to
this knowledge base, using the existing Semantic Layer journal theme.
