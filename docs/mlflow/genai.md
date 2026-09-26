# GenAI, Agents, Tracing, and Evaluation

MLflow 3.16.1 treats agent and LLM applications as a first-class workload.
The GenAI surface covers tracing, evaluation and monitoring, datasets,
feedback/assessments, version tracking, serving, and integrations.

Canonical sources:

- [MLflow for Agents and LLMs](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/genai/index.mdx)
- [Tracing](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/docs/genai/tracing)
- [Evaluation and monitoring](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/docs/genai/eval-monitor)
- [Evaluation datasets](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/docs/genai/datasets)
- [Version tracking](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/docs/genai/version-tracking)

## Tracing

Tracing records a tree of spans for an agent invocation. Spans can represent
model calls, retrieval, tool calls, reasoning steps, guardrails, and user
interactions. Attach inputs, outputs, metadata, token usage, cost, tags, and
links to make failures diagnosable.

Use automatic instrumentation for supported frameworks and manual tracing for
domain boundaries or custom tools. OpenTelemetry is the portability boundary:
MLflow can ingest or export trace data using OpenTelemetry conventions.

Canonical pages:

- [Tracing quickstart](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/genai/tracing/quickstart/index.mdx)
- [Automatic instrumentation](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/genai/tracing/app-instrumentation/automatic.mdx)
- [Manual tracing](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/genai/tracing/app-instrumentation/manual-tracing.mdx)
- [OpenTelemetry](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/genai/tracing/app-instrumentation/opentelemetry.mdx)
- [Trace search and UI](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/genai/tracing/search-traces.mdx)
- [Masking sensitive data](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/genai/tracing/observe-with-traces/masking.mdx)

For enterprise benchmarks, define a redaction policy before logging prompts,
tool arguments, retrieved documents, or user identifiers.

## Evaluation

GenAI evaluation supports evaluation datasets, built-in scorers, LLM judges,
custom code scorers, trace-based evaluation, multi-turn conversations,
conversation simulation, and regression testing.

Suggested benchmark flow:

1. Build a versioned evaluation dataset.
2. Run the agent with tracing enabled.
3. Attach deterministic metrics and judge-based scorers.
4. Store explanations, feedback, and assessments with the run/trace.
5. Compare against a baseline and gate regressions.

Canonical pages:

- [Evaluation quickstart](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/genai/eval-monitor/quickstart.mdx)
- [Evaluation overview](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/genai/eval-monitor/index.mdx)
- [Custom scorers](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/docs/genai/eval-monitor/scorers/custom)
- [LLM judges](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/docs/genai/eval-monitor/scorers/llm-judge)
- [Regression testing](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/genai/eval-monitor/regression-testing.mdx)
- [Assessments and feedback](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/docs/genai/assessments)

## Agent integrations

The tagged repository includes integrations for OpenAI Agents, LangChain,
LangGraph, DSPy, PydanticAI, Google ADK, CrewAI, AutoGen, LlamaIndex, smolagents,
Strands, and many model providers. The integration list is versioned and is
the authority for supported instrumentation.

[Integration listing](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/docs/genai/tracing/integrations/listing)

## Local benchmark policy

Record these fields for every agent run:

```text
agent.name, agent.version, framework, model, prompt.version
dataset.name, dataset.version, case.id
trace.id, run.id, latency_ms, token_usage, estimated_cost
score.*, failure.kind, failure.message, reviewer.feedback
```

Separate raw traces from derived summaries so a failed score can be
re-examined without rerunning the agent.

## Codex CLI tracing

Install the MLflow Codex notifier with Node.js 18 or newer:

```bash
npm install -g @mlflow/codex
```

Then configure this checkout and the active Codex home:

```bash
uv run agentbench configure-codex-tracing \
  --tracking-uri http://localhost:5000 \
  --experiment-id 0
```

The command adds the user-level Codex `notify` hook and writes
`.codex/mlflow-tracing.json` in the project. It refuses to replace a different
notifier. `MLFLOW_TRACKING_URI` and `MLFLOW_EXPERIMENT_ID` can override the
saved destination for an individual Codex process.

Start MLflow with `uv run mlflow server --port 5000`, then launch Codex from
the checkout. MLflow receives one conversation trace after each completed
turn. Prompts, responses, tool inputs, and user metadata may be sensitive, so
use an approved tracking server and retention policy.

Codex reads `notify` from its user configuration; project configuration cannot
define notification commands. See the
[Codex advanced configuration documentation](https://developers.openai.com/codex/config-advanced/)
and the MLflow Codex tracing integration documentation.
