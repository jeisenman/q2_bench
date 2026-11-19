# Hypothesis Agent

## Objective and scope

Add one registered Sol 6.1 hypothesis drafting role and a simple six-criterion
rubric. Use the existing Rust CLI -> API -> MCP contract and Agent Catalog.
Retain user acceptance before bounded research execution. No new service, tool,
autonomous loop, empirical data access, or persistent hypothesis entity.

## Research basis

Primary methodology sources reviewed on 2026-11-18 are linked in
[the agent guide](../agents/hypothesis/README.md): NIST statistical tests and
sample sizes, J-PAL randomized evaluations, and COS preregistration guidance.
The six criteria are project synthesis, not a standardized quality score.
They address specificity, measurement, falsifiability, credible comparison,
data feasibility, and prespecified/honest analysis.

## Implementation

- agents/hypothesis/agent.json: immutable hypothesis version 1, model gpt-6.1-sol,
  empty tools, drafting/review instructions and evidence boundaries.
- agents/hypothesis/example.md: hand-written draft for the user's first question,
  preserving ROE/profitability and expected/realized separation. Unknowns stay open.
- rc instructions: retrieve exact agent through agent_get and apply it as a role
  within the existing coordinator. Reuse prior answers; ask one missing question.
- Registration uses the existing Rust agent put operation. Changed instructions
  require a new version; identical registrations are idempotent.
- Tests cover persistent public API registration, restart readback, immutable
  conflicts, missing versions and no research creation. Rust checks cover role
  instruction delivery and the existing acceptance guard.
- MCP smoke accepts an optional exact agent ID/version and compares catalog/get
  results with the API after starting a new rebuilt MCP process.

## Validation

The live definition was registered in shared local MLflow through the Rust CLI.
Identical registration and HTTP readback passed. A fresh rebuilt MCP process
validated exact hypothesis/1 retrieval and catalog membership against the API.
No research or paid model invocation was performed by these operations.

The new API test passed against isolated SQLite-backed MLflow with filesystem
artifacts. Full repository checks and final evidence are recorded below.

## Limits

Tests establish storage, immutable identity, instruction delivery and acceptance
boundaries. They do not prove model compliance or scientific hypothesis quality.
The role uses the current conversation and supplied records; it does not promise
cross-session recall. Drafting does not preregister a study with an external
registry. The existing session-recording limitations still apply. A new rc
session is required to load updated coordinator instructions.

Final result: all 59 tests passed (29 Rust, 17 API, 13 TypeScript), plus formatting,
clippy, type checks, builds and the real SDK fixture closure. Fresh MCP exact-agent
and research HTTP parity passed. Agent definition registration remains identical
to the checked-in file. No paid model test or empirical execution was performed.
