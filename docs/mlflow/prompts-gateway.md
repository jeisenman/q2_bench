# Prompt Registry, AI Gateway, and MCP

## Prompt Registry

The Prompt Registry versions prompt templates and makes them discoverable and
reusable across applications. Use prompt versions for immutable history and
aliases for deployment-oriented pointers.

Canonical sources:

- [Prompt Registry overview](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/genai/prompt-registry/index.mdx)
- [Create and edit prompts](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/genai/prompt-registry/create-and-edit-prompts.mdx)
- [Use prompts in applications](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/genai/prompt-registry/use-prompts-in-apps.mdx)
- [Evaluate prompts](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/genai/prompt-registry/evaluate-prompts.mdx)
- [Prompt lifecycle aliases](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/genai/prompt-registry/manage-prompt-lifecycles-with-aliases.mdx)
- [Prompt optimization](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/genai/prompt-registry/optimize-prompts.mdx)

Benchmark rules:

- Give each prompt a stable name and semantic purpose.
- Record prompt name and version in every run.
- Treat a prompt alias like a deployment pointer and change it through review.
- Store the rendered prompt only when policy permits; otherwise log a redacted
  hash and the registry reference.
- Evaluate prompt changes against a fixed dataset before promotion.

## AI Gateway

The AI Gateway provides a common endpoint for model providers and can centralize
credentials, routing, fallbacks, rate limits, budgets, usage tracking, guardrails,
and traffic splitting.

Canonical sources:

- [AI Gateway overview](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/genai/governance/ai-gateway/index.mdx)
- [Gateway quickstart](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/genai/governance/ai-gateway/quickstart.mdx)
- [Provider endpoints](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/docs/genai/governance/ai-gateway/endpoints)
- [Keys and rotation](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/docs/genai/governance/ai-gateway/api-keys)
- [Limits and budgets](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/genai/governance/ai-gateway/budget-alerts-limits.mdx)
- [Fallbacks and traffic routing](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/genai/governance/ai-gateway/traffic-routing-fallbacks.mdx)
- [Guardrails](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/genai/governance/ai-gateway/guardrails.mdx)

Use the Gateway when provider access, cost controls, or credential isolation
must be managed centrally. Do not put long-lived provider secrets in
benchmark source or run parameters.

## MCP and MCP Registry

MLflow documents MCP support and an MCP Registry for registering servers,
managing versions/aliases, and connecting applications to servers.

- [MCP](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/genai/mcp/index.mdx)
- [MCP Registry](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/docs/genai/mcp-registry)

Treat tools exposed through MCP as untrusted execution boundaries. Record
server identity, tool name, input schema version, and authorization context in
the trace.
