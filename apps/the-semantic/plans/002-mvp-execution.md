# MVP execution plan

## Numeric success measure

Register one immutable agent. Run one accepted research plan with one SDK model
call. Retain question, hypothesis, experiment, run, output, metrics, trace and
agent digest in MLflow. Reload the API and Electron and inspect the same record.
Exercise one MCP read against that record and one sandboxed page plugin.

## Components and ownership

Coordinator owns protocol, root configuration, plans and integration evidence.
Rust worker owns crates/ and Cargo files. API worker owns server/ and example
JSON definitions. TypeScript worker owns apps/, packages/ and npm dependencies.
All workers use docs/protocol.md; cross-component changes go through coordinator.
There is no base commit in this newly initialized local repository. No commits,
remote repository or latest tracking branch are created without a real baseline.

## Sequence

1. Fix typed shared protocol before parallel implementation.
2. Build MLflow-backed routes, Rust CLI/MCP and SDK/Electron adapters.
3. Run unit and contract tests with fixture model output; no paid fixture calls.
4. Start fresh API/MCP processes and verify actual service configuration.
5. Perform one explicitly selected live gpt-5.6-sol SDK call.
6. Verify persistence after API restart, MCP read parity and iframe display.
7. Record checks, known gaps and run IDs without credentials or raw payload logs.

## Regression checks

Invalid/unaccepted plans, invalid limits, immutable agent conflicts, duplicate
submission, unknown IDs, provider failure, timeout, artifact failure, API restart,
SDK usage capture, CLI/MCP parity and iframe data boundaries. No tool activity or
model substitution may pass as a successful text-only run.

## Resources

Shared local MLflow 3.18.0 at 127.0.0.1:5055; app routes 127.0.0.1:5056;
Codex binary ~/codex/codex-rs/target/debug/codex; auth ~/.codex; Node 24+, Rust,
Python/uv for the MLflow adapter; local Electron and Chrome for UI QA.

## Status

Scaffold and MVP are implemented. Final verification and retained failures are
recorded in plans/003-validation.md. The successful live record survives restart.
