# Saved research proposals

## Objective and success criteria

User request: save the loan-scenario hypothesis and plan in the Researcher app,
then add draft saving when the existing app only supports accepted experiments.
Save one proposal, read it after service restart, and display it as DRAFT in a
separate app catalog. No model call or experiment acceptance occurs on save.

## Ownership and scope

The active scaffold-mvp worktree is the integration base. Its initial scaffold
is untracked; preserve it and all concurrent work. Root owns docs/protocol.md,
Python API/persistence/tests, integration and the user's saved proposal. Terra
owns apps/desktop and the standalone runtime proposal schema. Sol owns Rust
CLI/MCP and tests. The protocol is the authoritative common contract. Shared
schema output is authored once in packages/runtime/src/proposals.ts by Terra.
There is no database migration. Integrate backend and schemas, then consumers,
then one API/CLI/MCP/desktop end-to-end storage closure.

## Behavior

Proposal title, question, hypothesis and plan are immutable bounded text. Save,
list and get share the same API in desktop, CLI and MCP. DRAFT means unaccepted.
No agent, budget, experiment or attempt is created. The existing accepted
research flow stays unchanged. Revisions use a new explicit save key. No edit,
delete, automatic promotion or research execution is included.

Public MLflow operations store one separate proposal record. Pending writes
stay hidden and identical replays recover them. Native FINISHED means the
storage operation completed, not that a study ran. The shared tracking service
and its database schema are unchanged.

## Verification

Check field bounds, exact shapes, missing reads, sort direction, restart
persistence, idempotency, conflicts, partial-publication recovery, and absence
of research/experiment/attempt runs. Run public-client isolated MLflow tests,
desktop IPC/proxy tests, Rust/MCP tests, repository gates and fixture closure.
Rebuild API/CLI/MCP/desktop, restart the project API, save the actual user draft,
and read it through API, CLI and a fresh MCP process. Inspect the app if the
browser access host is available; otherwise report visual verification limits.

## Progress

- API and isolated persistence tests implemented; 13 proposal tests pass.
- Desktop and Rust integration complete. Full gate passes: 32 Rust, 30 API and
  15 TypeScript/runtime tests (77 total), formatting, clippy, type checks, builds
  and the real SDK fixture closure. The first concurrent full gate hit the
  existing native-startup two-second test deadline. That test passed alone and
  the full gate passed with RUST_TEST_THREADS=1; no unrelated test was changed.
- Project API restarted with the local-mlflow wrapper and the same experiment;
  the shared MLflow service was unchanged. The user's actual proposal is saved
  as dbf030bf05814426b47143e29f74b59e, DRAFT. API/CLI and a fresh rebuilt MCP
  process confirm identical save/list/get behavior and no duplicate proposal.
- All five pre-existing research IDs remain unchanged. No experiment or paid
  model call was started.
- Actual bundled Electron main/preload verified: exact draft and full plan
  display, same-key save replay with unchanged catalog count, invalid mutation
  rejection, sandbox/context isolation and blocked renderer Node/network.
  Screenshot var/proposal-desktop.png was visually inspected. The verified
  project Electron app was restarted with the existing session selection;
  the unrelated lineage app remains running. Browser host access was unavailable,
  so verification used the native Electron harness instead.
