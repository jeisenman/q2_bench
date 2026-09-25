# Serving and Deployment

MLflow supports local model serving, the deployment abstraction for target
platforms, classic model deployment integrations, and GenAI agent serving.

Canonical sources:

- [Classic deployment](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/classic-ml/deployment/index.mdx)
- [Local model deployment](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/classic-ml/deployment/deploy-model-locally/index.mdx)
- [Docker model serving](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/classic-ml/docker/index.mdx)
- [Deployment API reference](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/api_reference/source/python_api/mlflow.deployments.rst)
- [GenAI serving](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/docs/genai/serving)

## Local serving

For a registered or logged model, MLflow can expose a prediction endpoint:

```bash
mlflow models serve \
  --model-uri "models:/my-model@candidate" \
  --host 127.0.0.1 \
  --port 5001
```

Use a pinned model version or alias, a locked environment, and a health check.
Keep the serving process separate from the tracking server unless a local
development setup explicitly combines them.

## Deployment targets

MLflow deployment integrations may target Docker, Kubernetes, cloud ML
platforms, and vendor-specific serving systems. The supported target set and
required extras vary by release; consult the tagged deployment docs and the
`mlflow.deployments` API reference before standardizing a target.

Deployment decisions should specify:

- model URI and version/alias;
- environment and dependency lock;
- request/response schema;
- authentication and network policy;
- scaling and timeout limits;
- observability and rollback;
- cost and data-residency constraints.

## Agent and custom application serving

The GenAI serving docs cover agent servers and custom applications. Use these
when the deployed unit is an agent workflow rather than a single predictive
model.

- [Agent server](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/genai/serving/agent-server.mdx)
- [Custom apps](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/genai/serving/custom-apps.mdx)
- [Responses agent](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/genai/serving/responses-agent.mdx)

The deployed application must emit trace IDs that can be correlated with the
request, model/prompt versions, gateway route, and benchmark run.
