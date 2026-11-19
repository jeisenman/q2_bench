# Hypothesis Agent

This package owns the immutable hypothesis/1 catalog definition and its rubric.
It depends on the existing research API, MLflow catalog storage, and the Codex
interactive coordinator. It adds no API route, MCP tool, model bridge or agent loop.

agent.json is the executable instruction contract. README.md explains its six
criteria and sources. example.md applies the rubric to the user's first question.
Register through the existing Rust agent put command. Identical registration is
idempotent; change the version for any change after registration.

The rc coordinator reads the exact definition through semantic_research.agent_get
and applies it as a drafting role in its existing conversation. This does not
spawn an independent worker or execute an experiment. The empty tool list applies
to the definition; the coordinator retains its existing catalog-read capability.
Research execution still requires an explicitly accepted bounded specification.

Verify registration/readback, immutable conflicts, and no research creation in
server/tests/test_hypothesis_agent.py. Rust checks verify that rc forwards the
exact role/version and retains the acceptance guard. These checks prove storage
and instruction delivery, not the quality of a model-generated hypothesis.
