# Artifacts, Models, and the Model Registry

MLflow separates run metadata from artifacts. Artifacts are files associated
with a run, such as datasets, predictions, plots, logs, evaluations, model
directories, and trace exports.

Canonical sources:

- [Model and artifact docs](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/docs/classic-ml/model)
- [Artifact logging API](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/api_reference/source/python_api/mlflow.artifacts.rst)
- [Model Registry](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/docs/classic-ml/model-registry)
- [Model flavors](https://github.com/mlflow/mlflow/tree/v3.16.1/mlflow)

## Artifact design for benchmarks

Recommended run artifact layout:

```text
inputs/
predictions/
evaluation/
traces/
environment/
reports/
```

Store large or structured data as artifacts. Store small values needed for
search and filtering as metrics, parameters, or tags. Make artifact names
deterministic so reruns are easy to compare.

## Models

MLflow models are directories with an `MLmodel` description, an implementation
flavor, dependencies, and optional signature/input examples. The `pyfunc`
flavor gives a common prediction interface for custom Python models and many
framework integrations.

Important model concepts:

- Flavors: framework-specific loaders plus a common `pyfunc` interface.
- Signatures: declared input/output schema and tensor shapes.
- Input examples: representative inputs for discoverability and validation.
- Environment: `python_env.yaml`, `conda.yaml`, or requirements metadata.
- Models from code: define model behavior in source modules without relying on
  unsafe serialization patterns.
- Dependencies: pin runtime packages for reproducible serving.

Canonical pages:

- [Model overview](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/classic-ml/model/index.mdx)
- [Python model](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/classic-ml/model/python_model.mdx)
- [Models from code](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/classic-ml/model/models-from-code/index.mdx)
- [Signatures](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/classic-ml/model/signatures/index.mdx)
- [Dependencies](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/classic-ml/model/dependencies/index.mdx)

## Model Registry

The Registry provides a centralized model identity and lifecycle around model
versions. Use aliases and tags to separate mutable deployment pointers from
immutable versions.

Recommended benchmark workflow:

1. Log a model to the run.
2. Register it with a stable registered-model name.
3. Add the benchmark, dataset, and environment revisions as version tags.
4. Use an alias such as `candidate` or `champion` for deployment selection.
5. Keep the source run ID and artifact URI in the model version lineage.

The old stage-based workflow is not the preferred abstraction for new systems;
use aliases and explicit tags. Confirm behavior against the tagged Registry
docs before automating promotion.

Canonical pages:

- [Registry workflow](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/classic-ml/model-registry/workflow.mdx)
- [Registry tutorial](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/classic-ml/model-registry/tutorial.mdx)
- [Search registered models](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/classic-ml/search/search-models/index.mdx)

## Enterprise controls

Treat model artifacts as executable supply-chain inputs. Require review for
custom code, verify dependency lockfiles, scan containers, and restrict model
download/upload credentials. Never load untrusted pickled models in a
privileged process.
