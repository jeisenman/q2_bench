# One-turn SDK runtime

Build from the root with `npm run build:runtime`. Set SEMANTIC_CLI to the absolute
built researcher-codex executable. Rust invokes:

`node packages/runtime/dist/main.js --request /absolute/request.json`

The request and Completion contracts are in docs/protocol.md. The runtime uses
@openai/agents 0.22.0, a custom Rust Model adapter, one Agent/Runner turn, zero
retries and local metadata-only tracing. The optional bridge warning count is
validated and retained as provider_warning_count; absent legacy counts mean zero. Rust owns auth and MLflow persistence.
`npm test --workspace @the-semantic/runtime` uses no paid model calls.
