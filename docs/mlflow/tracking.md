# Tracking, Experiments, and Runs

MLflow Tracking records the inputs and outputs of work. A run belongs to an
experiment and can contain parameters, metrics, tags, datasets, artifacts,
models, and trace-linked assessments.

Canonical sources:

- [Tracking overview](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/docs/classic-ml/tracking)
- [Tracking API tutorial](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/docs/classic-ml/tracking/tracking-api)
- [Search experiments, runs, and models](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/docs/classic-ml/search)
- [Python client API](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/api_reference/source/python_api/mlflow.client.rst)

## Core data model

```text
Tracking URI
  └── Experiment
        └── Run
              ├── params: immutable inputs
              ├── metrics: numeric values, optionally step-based
              ├── tags: searchable metadata
              ├── datasets: input lineage
              ├── artifacts: files, tables, charts, reports
              ├── models: logged model versions
              └── traces / assessments: agent execution and quality
```

Use a stable experiment naming scheme for benchmarks, for example:

```text
benchmark/<group>/<benchmark>/<agent>/<dataset>/<split>
```

Put reproducibility identifiers in tags:

```text
benchmark.group
benchmark.name
benchmark.revision
agent.name
agent.revision
dataset.revision
environment.lock_hash
```

## Local and remote tracking

For a local developer loop:

```bash
uvx mlflow==3.16.1 server \
  --host 127.0.0.1 \
  --port 5000 \
  --backend-store-uri sqlite:///mlflow.db \
  --default-artifact-root ./mlartifacts
```

Then configure the client:

```python
import mlflow

mlflow.set_tracking_uri("http://127.0.0.1:5000")
mlflow.set_experiment("benchmark/data_transformation")

with mlflow.start_run(run_name="baseline") as run:
    mlflow.log_param("agent", "baseline")
    mlflow.log_metric("score", 0.82)
    mlflow.set_tag("benchmark.revision", "git-sha")
```

For enterprise use, point clients at a managed tracking server and keep
artifacts in an approved object store. Do not embed credentials in code or
benchmark manifests.

## Logging patterns

- Use explicit `start_run()` boundaries around each evaluated case or batch.
- Use nested runs for trials, folds, agent variants, or test cases.
- Log a metric at each meaningful step when a curve matters; use a final
  aggregate metric for ranking.
- Log inputs and outputs as artifacts when they are too large or sensitive for
  params/tags.
- Use `mlflow.log_input()` for dataset lineage.
- Use autologging only after reviewing what the integration captures.
- Enable system metrics when CPU, memory, GPU, or network behavior affects a
  benchmark.

Canonical pages:

- [Quickstart](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/classic-ml/tracking/quickstart/index.mdx)
- [Autologging](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/classic-ml/tracking/autolog/index.mdx)
- [System metrics](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/classic-ml/tracking/system-metrics/index.mdx)
- [Local database](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/classic-ml/tracking/tutorials/local-database/index.mdx)
- [Remote server](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/classic-ml/tracking/tutorials/remote-server/index.mdx)

## Querying benchmark results

Use MLflow search expressions to select runs by experiment, tags, metrics, and
parameters. For a benchmark leaderboard, materialize a small result table
with the run ID, agent revision, dataset revision, score, latency, cost, and
failure annotation IDs. Keep the raw run for full drill-down.

Avoid using a mutable display name as an identity. The stable identity is the
run ID plus the pinned revisions recorded in tags and artifacts.
