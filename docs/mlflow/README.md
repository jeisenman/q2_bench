# Local MLflow Documentation

This is an agent-friendly guide to MLflow for local and enterprise benchmarking.
It summarizes the official `mlflow/mlflow` repository at a pinned release and
links to the canonical tagged source for details that may change.

## Recommended baseline

Use **MLflow `3.16.1`** for this Python 3.11 project.

- Release: [MLflow 3.16.1](https://github.com/mlflow/mlflow/releases/tag/v3.16.1)
- Tag commit: `32792afe5b0183fce10532d3a023f5cfa8612d09`
- Release date: 2026-09-17
- Python requirement at the tag: `>=3.10`; Python 3.11 is supported.
- License: [Apache License 2.0](https://github.com/mlflow/mlflow/blob/v3.16.1/LICENSE.txt)

Pin both the package and the server image when reproducibility matters:

```text
mlflow==3.16.1
```

## Start with a use case

- [Tracking, experiments, and runs](tracking.md)
- [Artifacts, models, and the Model Registry](artifacts-models.md)
- [Projects, pipelines, and reproducible jobs](projects-pipelines.md)
- [GenAI, agents, tracing, and evaluation](genai.md)
- [Prompts, AI Gateway, and MCP](prompts-gateway.md)
- [Serving and deployment](serving-deployment.md)
- [Self-hosting, storage, and security](self-hosting-storage.md)
- [Integrations and plugins](integrations-plugins.md)
- [Python, REST, and CLI APIs](apis-cli.md)
- [Migration, upgrades, and troubleshooting](operations.md)
- [How to refresh these local docs](update.md)

## Functional map

| Need | MLflow capability | Local guide |
| --- | --- | --- |
| Compare benchmark runs | Experiments, runs, tags, metrics, search | [Tracking](tracking.md) |
| Preserve datasets and reports | Artifact stores and logged artifacts | [Artifacts](artifacts-models.md) |
| Package an agent or model | Models, `pyfunc`, signatures, flavors | [Models](artifacts-models.md) |
| Promote versions | Model Registry, aliases, tags, webhooks | [Models](artifacts-models.md) |
| Observe agent behavior | Traces, spans, feedback, assessments | [GenAI](genai.md) |
| Score agent quality | Evaluation datasets, scorers, judges | [GenAI](genai.md) |
| Version prompts | Prompt Registry and prompt aliases | [Prompts](prompts-gateway.md) |
| Control model access | AI Gateway, keys, limits, fallbacks | [Prompts](prompts-gateway.md) |
| Run locally or remotely | MLflow server, serving, deployments | [Serving](serving-deployment.md) |
| Operate securely | Backend/artifact stores, auth, SSO, RBAC | [Self-hosting](self-hosting-storage.md) |

## Repository provenance

These documents were written from the official repository, not copied from
MLflow application source:

- Repository: [mlflow/mlflow](https://github.com/mlflow/mlflow)
- Pinned tree: [v3.16.1](https://github.com/mlflow/mlflow/tree/v3.16.1)
- Documentation tree:
  [docs/docs](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/docs)
- API reference:
  [docs/api_reference](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/api_reference)
- License text:
  [LICENSE.txt](https://github.com/mlflow/mlflow/blob/v3.16.1/LICENSE.txt)
- Retrieved and reviewed: 2026-09-25

This local set is a practical index and operating guide. It is not a
redistributed copy of MLflow's full website or generated API reference.
