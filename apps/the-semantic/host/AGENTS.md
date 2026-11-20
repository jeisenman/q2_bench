# Finite host reads

`gherkin-read.ts` is a Node entry for the existing research API. It accepts one
bounded JSON request on stdin and reuses the desktop's committed-Git source
reader and strict contracts. It writes one validated JSON response; failures
expose a static category, never child diagnostics. No credentials, models,
embeddings, index writes, or source execution belong here.

Build with `npm run build:host` from the app root. The ignored `dist-host` output
is required before API keyword reads. The API bounds this child's output and
lifetime and terminates its owned process group. No new MCP service is created.
