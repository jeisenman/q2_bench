# Integrations and Plugins

MLflow integrates with traditional ML frameworks, deep-learning libraries,
LLM providers, agent frameworks, cloud platforms, storage systems, and
observability tooling.

Canonical sources:

- [GenAI integration listing](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/docs/genai/tracing/integrations/listing)
- [Classic ML plugins](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/classic-ml/plugins/index.mdx)
- [Python API reference modules](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/api_reference/source/python_api)
- [Repository integrations](https://github.com/mlflow/mlflow/tree/v3.16.1/mlflow)

## Integration categories

### ML and deep learning

The tagged API reference includes integrations for scikit-learn, XGBoost,
LightGBM, CatBoost, Spark ML, PyTorch, TensorFlow, Keras, Transformers,
Sentence Transformers, ONNX, spaCy, Prophet, statsmodels, H2O, and others.

### Agents and LLMs

The tagged GenAI docs list integrations for OpenAI, Anthropic, Bedrock,
Gemini, Groq, Mistral, Cohere, LangChain, LangGraph, DSPy, LlamaIndex,
PydanticAI, Google ADK, CrewAI, AutoGen, smolagents, Strands, and many more.

### Observability

OpenTelemetry is the portability layer. MLflow can instrument supported
libraries automatically or accept manual spans and exported trace data.

## Choosing an integration

For each integration, record:

```text
package and version
MLflow extra or optional dependency
automatic vs manual instrumentation
captured fields and redaction behavior
supported Python/runtime versions
network and credential requirements
```

Keep optional integrations out of the core environment unless a benchmark uses
them. Add extras to a separate lock or container so the baseline remains
reproducible.

## Plugin extension points

Plugins and integrations can extend model flavors, deployment targets,
authentication, storage, tracing, or provider behavior. Prefer documented
entry points and public interfaces. Keep adapters behind a typed local
interface and test them against a pinned MLflow server.

Do not import MLflow private modules as an extension contract. Private modules
can change between patch releases.

## Compatibility checklist

- Test client/server version compatibility.
- Test offline behavior if the benchmark must run without internet.
- Verify artifact URI handling for the target store.
- Verify trace serialization and payload size limits.
- Verify provider retries, timeouts, and rate limits.
- Capture the integration version in every run.
