# Gherkin behavior knowledge base

Gherkin specifications describe expected application behavior. The Semantic has
a separate Gherkin knowledge base for this evidence. It does not convert the
specifications into approved SME definitions or claim that a scenario passed.

## Located sources

The local inventory on November 19, 2026 found 334 tracked `.feature` files in
`pl-application`, at commit
`5af19e313f0012911d695abb6cf1690650a24874`:

| Source directory | Feature files |
| --- | ---: |
| Boa.TestCases.PrecisionLenderV2 | 237 |
| Boa.TestCases.AndiSkillsV2 | 47 |
| Boa.TestCases.IntegrationsV2 | 36 |
| Boa.TestCases.FinancialStatementsV2 | 11 |
| Boa.TestCases.ContainerEnvironment | 2 |
| Boa.Tool.DatabaseRecovery | 1 |

Examples include opportunity loan rate locks, initial payment skills, API v2
opportunity updates, relationships, treasury, and rate sheets. These are file
counts, not scenario counts or runtime test results. Scenario outlines can
describe more than one test case.

The separate `andi-boa-tests` repository has 23 tracked `.feature` files under
`tests/Andi.Boa.Specs/Features`, at commit
`53d05f5040549a5fa618c6ddc44ee603efc3b368`. It covers behavior such as skill
drafts, API keys, and chat configuration. This secondary repository is recorded
for discovery. The initial application knowledge base reads one configured
checkout; it does not combine these repositories without source selection.

## Read contract

The app lives under `apps/the-semantic`. Configure its trusted host setting
`SEMANTIC_GHERKIN_ROOT` to select a local `pl-application` checkout. The renderer
cannot supply a filesystem root or run a Git command. The source must be a Git
checkout with committed `.feature` files.

List and search operations use committed source. Feature detail keeps the exact
commit selected in the results. Uncommitted edits are not imported. Search is
literal text search; it does not infer a relationship to a lineage node or a
Help Center article. The detail shows the original Gherkin, including tags,
backgrounds, scenario outlines, and examples. Files are read as evidence, never
executed.

Bounds and strict request validation apply at the host boundary. Missing source,
invalid commits, invalid paths, and exceeded limits return explicit errors. The
view cannot silently substitute another source. A source commit identifies the
specification revision; it does not establish which revision is deployed.

## Semantic integration

PL-App Behavior is a peer of Lineage, Zendesk, Definitions, Repositories, and Research.
It supplies application behavior evidence through the existing finite desktop
read bridge. It creates no semantic service and makes no model calls. Any later
mapping from a scenario to a dataset, column, or business definition must retain
the source commit and path and have its own supporting evidence.

The agent responsible for the semantic app import was informed of this source,
the separate knowledge base, and its evidence boundary. The implementation uses
the imported app in the current `qtwo_bench` checkout.
