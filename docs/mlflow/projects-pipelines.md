# Projects, Recipes, and Reproducible Jobs

## MLflow Projects

Projects describe reproducible entry points, parameters, environments, and
source revisions. They are useful when a benchmark should run from a Git
repository in a clean environment rather than from the current checkout.

Canonical source:

[Classic ML Projects](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/classic-ml/projects/index.mdx)

Use Projects when the benchmark needs:

- a Git commit or repository URI as the execution source;
- named entry points such as `train`, `evaluate`, or `score`;
- declared parameters and default values;
- a managed Conda, virtualenv, or container environment;
- a consistent handoff between local and remote execution.

For this repository, benchmark manifests should record the repository URI and
immutable commit SHA. The runner should pass only validated parameters and
should capture the project revision in MLflow tags.

## Recipes and Pipelines

The `v3.16.1` tagged docs tree has strong first-class coverage for Projects,
model training, evaluation, deployment, and GenAI workflows, but does not
expose a current top-level `Recipes` or `Pipelines` documentation section.
Treat MLflow Recipes/Pipelines as legacy or version-specific functionality
until a target deployment confirms support.

For new benchmark orchestration, use a thin explicit workflow around:

1. dataset acquisition and validation;
2. agent/model execution;
3. MLflow run creation;
4. artifact and trace logging;
5. evaluation and annotation;
6. result publication.

Keep orchestration in the benchmark runner or an external scheduler. Do not
make MLflow Projects responsible for secrets, policy decisions, or arbitrary
network access.

Relevant tagged documentation:

- [Classic ML index](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/classic-ml/index.mdx)
- [Traditional ML](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/classic-ml/traditional-ml/index.mdx)
- [Deep learning](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/classic-ml/deep-learning/index.mdx)
- [Training tutorials](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/classic-ml/tutorials-and-examples/index.mdx)

## Benchmark execution contract

Each benchmark invocation should have:

```text
source: repository + commit
inputs: dataset identifier + revision
entrypoint: project entry point or agent callable
environment: lockfile/container digest
outputs: score table + artifacts + traces
status: passed, failed, timed out, or cancelled
```

Use a parent run for the benchmark and nested runs for cases or variants.
That layout supports aggregate scoring while preserving individual failures.
