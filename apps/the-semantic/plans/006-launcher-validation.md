# Interactive launcher validation

The rc alias was added as one line after bc in ~/.bash_profile. All other profile
bytes and the file mode were preserved. bash -n passes. The full profile was not
sourced for validation. A clean shell loaded only the new alias line.

## Local evidence

The full Rust launcher opened actual Electron and used the live application API
and shared MLflow service. Its deterministic Codex fixture submitted two clearly
labelled messages through the session-specific OTLP endpoint. No model was called.

- Session: 687c9e73981f4328857e6642a1ca1258
- MLflow trace: tr-6623a8b76f2963ffa837ca30da6af4b7
- Model selection: gpt-6.1-sol, asserted by the fixture
- Result: CLOSED, exit 0, two messages and four retained events
- Tracking service: http://127.0.0.1:5055, experiment 2
- App API: http://127.0.0.1:5056

The API and Electron remained available after the child exited. rc --check
confirmed the exact project, tracking service, session capability and default
Codex binary. Unit and integration checks also cover terminal failures, cleanup,
redaction, event limits, restart persistence and no model substitution.

The first full quality run passed 26 Rust, 16 API and 13 TypeScript tests, type
checks, formatting, clippy, builds and the real Agents SDK closure with a fixture.
The API tests use an isolated real MLflow store for persistence and trace checks.

## Limits

The older local embedded runtime rejected gpt-6.1-sol. The user confirmed a
successful working bc Enterprise session on the managed 0.170.0 server runtime.
Native startup alone is not a successful inference. No paid prompt is submitted
by startup.
Session capture is selected native log evidence and an application summary trace;
it does not include native internal spans or hidden reasoning. User messages and
main-agent responses are recorded. Known credential patterns are filtered; an
arbitrary secret can still appear as ordinary text. Tool payloads are discarded.

API and Electron intentionally remain running after a successful chat launch.
A force-killed launcher or machine failure can leave an ACTIVE session; automatic
crash recovery is not implemented. The UI uses manual refresh and shows snapshot
freshness. The existing one-attempt accepted-experiment path remains separate.

## Final startup checks

Actual Electron displayed the exact fixture session, both messages, counts, model
and trace. The second Electron process reused one window and selected that same
record. A macOS argv reordering defect was fixed with validated single-instance
metadata. Production isolation, CSP and finite IPC checks passed.

A newly created research MCP process exposed all five tools and returned an exact
HTTP-equivalent existing research record. No research execution was requested.
Native Codex started through the installed alias with the real default binary
and reached its normal folder-trust screen. Escape quit without saving a trust
decision or submitting a prompt. Session bfb49e83a92443418033a27370c5bce9
closed with exit 0, zero messages, two lifecycle events, and summary trace
tr-9ac4baf0683e427c06f2a035c530dc43. First use still requires the user to make
the native folder-trust decision. Model inference remains untested in this check.

The per-invocation MCP overlay now correctly handles actual server names instead
of creating literal-quoted names. User config/authentication remain intact and
unrelated servers are disabled for this research child. Final Rust 26 checks and
fresh MCP API parity passed after rebuilding; final TypeScript 13 checks and
native session checks passed after rebuilding Electron.

## Managed runtime alignment

The tracing -c overrides force private embedded mode in the local Codex fork.
The previous launcher therefore used its old 0.0.0 server, while bc used the
managed 0.170.0 background server. Chat now selects the validated installed
managed current runtime. Explicit CODEX_BINARY still wins. Accepted-experiment
execution is unchanged. The shared background server is not restarted.

Before the default resolver change, an explicit 0.170.0 runtime launch reached
the native prompt showing GPT-6.1-Sol medium, accepted the recording configuration,
and quit normally without a model prompt. Remaining startup warnings concern the
user models setting, deprecated multi_agent setting, and expected private mode.

The final default chat --check resolves the installed 0.170.0 binary and explicit
gpt-6.1-sol. The full quality command passes 29 Rust, 16 API and 13 TypeScript
tests, formatting, types, builds and SDK closure. A fresh rebuilt MCP process
passes five-tool and HTTP-parity checks. The native installed-runtime session
closed with a summary trace and no model prompt. No inference was performed.

Normal session views now omit raw session and trace IDs, showing title/date and
trace retention instead. Research technical IDs are collapsed. The packaged
result plugin no longer prints the attempt ID. Native exact-record and
single-instance checks passed with IDs used internally; the latest app reopened
the user-selected session with the readable UI.
