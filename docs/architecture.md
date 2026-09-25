# Project architecture

## Purpose

`q2-bench` provides typed building blocks for defining, benchmarking, tracing,
and reviewing agent applications locally.

## Layout

```text
src/                Public library packages
tests/              Tests mirroring production modules
scripts/            Repository quality and policy checks
docs/               Local, agent-readable documentation
```

## Dependency direction

```text
application/integrations
          |
          v
    q2-bench APIs
          |
          v
 pure domain and vector logic
```

Core modules must not depend on provider SDKs, network clients, or application
configuration. Integrations should adapt external SDK objects into local typed
interfaces.

## Public API

Only names deliberately exported from package `__init__.py` files are
considered public. New public behavior requires:

1. Typed implementation.
2. Boundary and failure tests.
3. A concise local documentation update.
4. A clean `uv run python scripts/check.py` run.

## Design rules

- Prefer immutable values and explicit dependencies.
- Batch numeric work and use NumPy array operations.
- Validate shape, dimensionality, and finite values at boundaries.
- Keep provider-specific concerns in dedicated integration modules.
- Persist local benchmark runs and annotations in SQLite.
- Use Inspect AI tasks as the benchmark execution boundary.
- Split modules by responsibility before they approach 400 lines.
