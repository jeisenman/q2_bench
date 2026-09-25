# Python, REST, CLI, and API References

MLflow exposes a Python client, command-line interface, REST endpoints, and
generated API references. Use the public API references for implementation and
keep this file as the navigation map.

Canonical sources:

- [API reference root](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/api_reference/source)
- [Python API index](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/api_reference/source/python_api/index.rst)
- [REST API](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/api_reference/source/rest-api.rst)
- [CLI reference](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/api_reference/source/cli.rst)
- [Java API](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/api_reference/source/java_api)
- [TypeScript API](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/api_reference/source/typescript_api)

## Python API areas

The tagged reference includes modules for:

- tracking and `MlflowClient`;
- entities, exceptions, configuration, and environment variables;
- artifacts, models, model flavors, and model registry;
- projects, deployments, server, and gateway;
- data, metrics, tracing, GenAI, and system metrics;
- framework-specific integrations and autologging.

Start with the high-level `mlflow` API for normal application code and
`MlflowClient` for explicit administrative or automation workflows.

## CLI areas

The CLI includes commands for common server, model serving, run, artifact,
project, and environment workflows. Always run:

```bash
mlflow --help
mlflow <command> --help
```

against the pinned installation because command options can change.

Useful starting commands:

```bash
mlflow server --help
mlflow run --help
mlflow models serve --help
mlflow artifacts --help
mlflow experiments --help
mlflow runs --help
```

## REST API

Use REST when the benchmark runner is not Python or when a service boundary is
required. The tagged API reference is the contract for endpoints, request
schemas, pagination, and error handling. Generate or inspect the OpenAPI
surface for the exact server configuration used in production.

Authentication, TLS, proxy behavior, and artifact URLs are deployment concerns
and must be tested separately from endpoint serialization.

## API usage rules

- Pin the client package and server image.
- Prefer stable public APIs over private imports.
- Add timeout and retry policies at the adapter boundary.
- Log request correlation IDs, not secrets.
- Validate pagination and eventual consistency.
- Test failure status codes and partial artifact failures.
