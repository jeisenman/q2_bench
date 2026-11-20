# SDK runtime

This package performs one accepted text-only experiment. `contracts.ts` owns
strict wire validation. `run.ts` sets up one Agent, one Runner and a local SDK
trace processor. `bridge.ts` implements the Model interface by spawning the
absolute Rust executable from SEMANTIC_CLI. Credentials and provider execution
remain in Rust/Codex. No tools, streaming, retries or model substitution.

`dist/main.js --request <path>` prints only Completion JSON for valid requests.
Invalid requests exit 2 before model execution. Runtime failures return terminal
Completion evidence. Events contain IDs and event types only. Never retain raw
provider stderr or prompt content in trace events. Tests use executable fixtures;
never call a paid provider in this package's test command.
