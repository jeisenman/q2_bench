# Repository instructions

## Mission

Build a reliable, typed Python SDK for agent workloads. Prefer simple modules,
explicit contracts, vectorized batch operations, and deterministic behavior.

## Toolchain

- Use `uv` for environments, dependencies, locking, and command execution.
- Support Python 3.11 and newer.
- Use NumPy for numeric batch operations; avoid Python loops over vectors where
  an equivalent array operation is clearer.
- Run `uv run python scripts/check.py` before declaring work complete.

## Architecture

- Production code belongs in top-level packages under `src/`.
- Data-engineering agents belong in
  `src/workspaces/data_engineering/agents/<agent_name>/`.
- Every agent must be its own package directory.
- Every agent package must contain an `AGENTS.md` that follows
  `docs/agent-documentation-standard.md` and documents its architecture,
  dependencies, and workflow.
- When an agent implementation approaches or exceeds 400 lines, split it into
  focused modules such as dates, tools, classification, reporting, and data.
- Workspace benchmark tasks belong in
  `src/workspaces/data_engineering/benchmarks/`.
- Runtime containers and connector configuration belong outside `src/`.
- Reproducible analysis belongs in the top-level `investigations/` directory.
- Tests mirror production modules under `tests/`.
- Keep integrations behind typed `Protocol` interfaces.
- Keep pure domain logic independent from network and provider SDKs.
- Public APIs must be exported deliberately from package `__init__.py` files.
- Prefer immutable dataclasses and dependency injection over global state.

## Code rules

- No tracked source or documentation file may exceed 400 lines.
- Add type annotations to all production functions.
- Add concise docstrings to public modules, classes, and functions.
- Raise specific exceptions with actionable messages.
- Use fail-fast code: validate required inputs and configuration at boundaries,
  stop immediately on invalid state, and avoid silent fallbacks or partial work.
- Never hide lint or type failures with broad ignores.
- Never commit secrets, credentials, generated environments, or caches.
- Add tests for success, boundary, and failure behavior.

## Change workflow

1. Read `docs/README.md`, then nearby code and tests before editing.
2. Keep changes scoped and preserve backward compatibility unless requested.
3. Update tests and documentation with behavior changes.
4. Update the agent's `AGENTS.md` when its architecture, dependencies, or
   workflow changes.
5. Run the repository quality command.
6. Summarize changed behavior, verification, and remaining risks.

## Anti-leak benchmark protocol

- Invoke the anti-leak agent whenever creating or changing an agent benchmark,
  its public assets, hidden expectations, matrix, container, mounts, or runtime
  security profile.
- Run this audit concurrently as a side process. A Sol controller must
  coordinate Luna subagents for independent public-versus-hidden data checks
  and container-security checks.
- The audit must inspect sanitized metadata only. Never ask a reviewer to print
  secret values or broadly enumerate host files.
- Fail closed when public assets expose expected answers, credentials are
  copied into an image, hidden data is mounted into a candidate container, or
  the runtime has an unjustified privileged security profile.
- Convert every confirmed, reproducible leakage into a dated anti-leak
  benchmark case with sanitized evidence, a protected expected finding, and a
  regression assertion.
- Do not encode speculative findings as expected answers. Record uncertain
  observations as review gaps until independently evidenced.
