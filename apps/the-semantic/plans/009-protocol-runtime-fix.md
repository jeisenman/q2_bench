# Protocol review runtime repair

## Objective and scope

Produce one FINISHED protocol review with nonempty output using immutable
hypothesis/1, model gpt-6.1-sol. No empirical loan-data access or ROE estimation.
The failed review 9d8b36ba33f74cfaafc3e73be1517e1c stays retained unchanged.
The user requested a fix loop; confirmation of a proposed ceiling of three
new model attempts of 180 seconds each is pending. No new live attempt begins
before that confirmation. Each accepted experiment remains one call/attempt;
do not add application retries or model fallback.

## Diagnosis

The experiment bridge defaults to ~/codex/codex-rs/target/debug/codex, reporting
version 0.0.0. Interactive chat resolves the managed active installation, which
reports version 0.170.0. CODEX_BINARY is unset. The managed executable reports
ChatGPT login; authentication contents were not read. Both exec help commands
support the required flags. This is a verified path/version mismatch and a
candidate explanation, not proof that model access is fixed.

## Change and regression checks

Root owns the bridge, new fixture tests and this documentation. An independent
one-pass Sol assessment agreed to reuse installed_codex::resolve. Reuse the
existing codex_home boundary for CODEX_HOME/HOME selection. Chat, doctor and
experiments then use the same validated active runtime with explicit override
precedence. Keep the model, isolation flags, parser, warnings and deadlines.

Offline fixtures check managed-current execution with HOME absent, unchanged
model/prompt/isolation, explicit override precedence, invalid override failure,
and missing active pointer rejection despite a legacy debug-binary decoy.
Run the existing Rust/runtime/API/desktop gates before any permitted live check.
Use only public MLflow and existing API routes to retain future attempts; do
not inspect or copy tokens or write raw provider logs.

## Live-check gate

After confirmed scope and offline checks, rebuild the CLI and start a fresh MCP
process. Record each new accepted specification and unique idempotency key.
At most three new attempts, 180 seconds each, stopping immediately after the
first FINISHED record with nonempty output. A persistent model-access or
authentication error remains explicit and does not permit a substitute model.

## Offline verification

The three new runtime-selection tests pass. The full repository gate passes
with RUST_TEST_THREADS=1: 35 Rust, 30 API, 24 desktop and 5 runtime tests (94
total), plus formatting, clippy, type checks, builds and fixture SDK closure.
Concurrent Semantic Layer changes account for additional desktop coverage;
those edits were preserved. Doctor now reports the validated managed 0.170.0
executable. No new provider call has been made; live scope confirmation remains
pending. The runtime repair is verified offline, not yet against Sol 6.1.
