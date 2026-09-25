# Migration, Upgrades, and Troubleshooting

## Upgrade policy

Pin the baseline to MLflow `3.16.1` and upgrade deliberately. For each upgrade,
record the old and new versions, release notes, dependency diff, schema
changes, API changes, and benchmark result deltas.

Canonical sources:

- [MLflow releases](https://github.com/mlflow/mlflow/releases)
- [Changelog at v3.16.1](https://github.com/mlflow/mlflow/blob/v3.16.1/CHANGELOG.md)
- [Self-hosting migration](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/self-hosting/migration.mdx)
- [File-store migration](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/self-hosting/migrate-from-file-store.mdx)
- [Self-hosting troubleshooting](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/self-hosting/troubleshooting.mdx)

## Upgrade checklist

1. Read the release notes and tagged docs.
2. Rebuild the `uv` lock or serving image with the target version.
3. Run tracking, artifact, registry, tracing, evaluation, and serving smoke
   tests.
4. Exercise migrations against a database copy.
5. Compare API help output and generated schema where relevant.
6. Re-run a fixed benchmark corpus and compare scores, latency, cost, and
   failure annotations.
7. Promote only after rollback and restore procedures pass.

Do not upgrade a tracking server independently of clients without testing
compatibility. Keep backups before database migrations.

## Common failure classes

### Tracking connection failures

Check the tracking URI, DNS/TLS, authentication headers, proxy configuration,
server health, and client/server versions. Reduce the problem to a small
`MlflowClient` request before retrying a full benchmark.

### Artifact upload or download failures

Check the artifact root, credentials, bucket/container permissions, network
egress, URI scheme, and object size limits. Verify whether clients access
artifacts through the server or directly.

### Run appears incomplete

Inspect run status, nested-run relationships, process termination, flush/close
behavior, and server logs. Use deterministic run IDs and write a final status
artifact when the runner can be interrupted.

### Traces are missing or oversized

Check instrumentation initialization order, sampling, exporter configuration,
redaction, payload limits, and asynchronous flush. Capture a trace ID in the
benchmark result even when the trace is partial.

### Evaluation is nondeterministic

Separate deterministic metrics from LLM judges. Pin judge model/configuration,
dataset revision, scorer version, prompt version, and temperature. Persist
judge explanations and raw assessment data.

### Serving fails to load a model

Inspect the model flavor, signature, runtime dependencies, Python version,
artifact access, and model code policy. Reproduce with a minimal local serving
container before testing a cloud target.

## Security and incident handling

Treat traces, prompts, artifacts, and model files as potentially sensitive.
When a run is unsafe or incorrect, annotate the run with a structured failure
kind, preserve the evidence needed for review, and avoid copying secrets into
logs or issue reports.
