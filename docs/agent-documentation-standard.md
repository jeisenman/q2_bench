# Agent documentation standard

Every agent package under `src/workspaces/data_engineering/agents/` must contain
an `AGENTS.md`. The document is part of the agent's implementation contract and
must change with any material architecture, dependency, or workflow change.

## Required structure

Use these exact second-level headings:

```markdown
# <Agent name>

## Purpose

State the agent's responsibility, users, inputs, outputs, and safety boundary.

## Architecture

Name the entry point and each module or component. Describe responsibility,
state ownership, concurrency, integration boundaries, and public API.

## Dependencies

List internal packages, injected protocols, external services or SDKs, runtime
configuration, and why each dependency is needed. Write `None` where a category
does not apply; do not omit it.

## Workflow

Describe the ordered path from request validation through output. Include
branching, parallel work, failure behavior, and externally visible side effects.

## Verification

Name the focused tests, benchmarks, and operational signals that verify the
documented design.

## Change policy

Identify changes that require this document to be updated.
```

## Content rules

- Describe current implemented behavior, not intended future behavior.
- Link module names using repository-relative paths.
- Call out read/write boundaries and production mutations explicitly.
- Keep provider details behind the same typed interfaces used by the code.
- Prefer a short Mermaid diagram when three or more components interact.
- Do not duplicate prompts, credentials, generated schemas, or upstream API
  documentation.
- Keep the file below the repository's 400-line limit.

## Enforcement

`uv run python scripts/check.py` verifies that every agent package has an
`AGENTS.md` with the required sections and non-placeholder content.
