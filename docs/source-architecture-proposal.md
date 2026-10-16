# Source Architecture Proposal

## Decision

Use installable top-level Python packages under `src/`, with lowercase
`snake_case` directories. Place the data-engineering domain under
`workspaces.data_engineering`; place contracts in `ports`;
place MLflow, data-platform, agent-framework, and local-storage implementations
in `adapters`.

Use MLflow 3.16.1 as the system of record for experiments, runs, traces,
assessments, artifacts, prompts, and deployable model or agent versions. Use
Inspect AI as the benchmark execution boundary and Click as a thin CLI. Keep
agent definitions framework-neutral, with OpenAI Agents SDK or another agent
framework selected through an adapter.

Reviewed against the local MLflow 3.16.1 documentation on 2026-09-25.

## Shortcomings in the base layout

The proposed shape has the right domain and integration concepts, but it needs
the following corrections before implementation:

- `Workspace`, `Ports`, `Adapters`, and `Benchmarks` are not valid project
  package conventions. Python packages should be lowercase, and all production
  packages must remain under the configured `src/` package root.
- Filesystem nesting is useful for ownership, but it is not sufficient
  benchmark identity. Directories can move; IDs and revisions must not.
- A global `ports/` or `adapters/` directory can become a junk drawer. Ports
  must describe capabilities needed by the domain, and adapters must be grouped
  by external system.
- Real and mock data access should not be implemented separately inside every
  agent. Agents consume the same typed data ports; production and test
  composition inject different adapters.
- Hidden answers inside an installable package are discoverable by the agent
  under evaluation and can be included in wheels or containers.
- MLflow objects must not leak into benchmark, agent, or scoring logic. That
  would couple the domain to one tracking product and make deterministic tests
  harder.
- Runs, traces, scores, artifacts, and reviewer feedback need one correlation
  model. A separate custom SQLite run database would create conflicting sources
  of truth when MLflow already provides these records.

## Dependency direction

```text
cli / composition root
        |                     |
        v                     v
workspace services -------> ports <------- adapters
        |                     ^                |
        v                     |                v
domain models ---------------+       MLflow, data systems,
                                      agent frameworks, files
```

Rules:

1. Domain models have no dependency on MLflow, Click, Inspect AI, provider
   SDKs, network clients, environment variables, or filesystem configuration.
2. Workspace services orchestrate domain models and ports.
3. Ports contain typed `Protocol` contracts and domain-shaped values.
4. Adapters implement ports and may depend on external SDKs.
5. The CLI/composition root is the only layer that selects concrete adapters.
6. Adapters may import ports and domain values; ports and workspaces never
   import adapters.

## Recommended implementation tree

```text
src/
├── domain/
    │   ├── agents.py
    │   ├── benchmarks.py
    │   ├── evaluations.py
    │   ├── failures.py
    │   └── identifiers.py
├── ports/
    │   ├── agent_runtime.py
    │   ├── artifacts.py
    │   ├── datasets.py
    │   ├── evaluations.py
    │   ├── secrets.py
    │   └── tracking.py
├── adapters/
    │   ├── mlflow/
    │   │   ├── tracking.py
    │   │   ├── tracing.py
    │   │   ├── evaluation.py
    │   │   └── registry.py
    │   ├── data/
    │   │   ├── databricks.py
    │   │   ├── snowflake.py
    │   │   └── oms.py
    │   ├── agent_frameworks/
    │   │   ├── openai_agents.py
    │   │   └── inspect_ai.py
    │   └── local/
    │       ├── datasets.py
    │       └── secrets.py
├── workspaces/
│   └── data_engineering/
    │       ├── benchmarks/
    │       │   ├── catalog.py
    │       │   └── groups/
    │       │       └── data_transformation/
    │       │           ├── group.yaml
    │       │           ├── benchmark_one/
    │       │           │   ├── manifest.yaml
    │       │           │   ├── task.py
    │       │           │   ├── scorers.py
    │       │           │   └── public/
    │       │           └── benchmark_n/
    │       ├── agents/
    │       │   └── transformation_agent/
    │       │       ├── definition.py
    │       │       ├── instructions.py
    │       │       └── tools/
    │       └── services/
    │           ├── run_benchmark.py
    │           └── review_run.py
├── cli/
    │   ├── main.py
    │   ├── benchmarks.py
    │   └── runs.py
└── config/
        ├── models.py
        └── loading.py
```

`workspace` should be plural because the package can host additional bounded
contexts later. A benchmark directory should use `benchmark_one`, not
`benchmark1`, when a descriptive name is unavailable. Prefer meaningful names
such as `normalize_customer_records`.

## Benchmark identity and MLflow mapping

Every benchmark manifest should contain immutable identity fields:

```yaml
schema_version: 1
benchmark_id: data_engineering.data_transformation.normalize_customer_records
benchmark_version: 1.2.0
group_path:
  - data_engineering
  - data_transformation
source_revision: "<git-commit>"
dataset:
  id: customer_records
  revision: "<content-digest-or-version>"
```

Validate the catalog at startup: IDs must be globally unique, group components
must be `snake_case`, versions must be valid, and source/data revisions must be
pinned. Directory names are discoverability aids, not identity.

Use this MLflow hierarchy:

| Concept | MLflow representation |
| --- | --- |
| Data-engineering benchmark group | Experiment: `q2_bench/data_engineering/data_transformation` |
| One suite invocation | Parent run |
| One benchmark/agent variant | Nested child run |
| One case, trial, or fold | Nested leaf run or trace, based on volume |
| Searchable dimensions | Flat tags |
| Fixed invocation settings | Parameters |
| Numeric outcomes | Metrics |
| Reports, predictions, logs | Artifacts |

Do not create an experiment per agent, dataset split, or case. That produces
high-cardinality administration and makes comparison harder. Keep the
experiment stable at the benchmark-group boundary.

Required run tags should include:

```text
workspace
benchmark.group_path
benchmark.group.0
benchmark.group.1
benchmark.id
benchmark.version
benchmark.source_revision
agent.id
agent.version
agent.framework
dataset.id
dataset.revision
dataset.split
environment.lock_hash
environment.container_digest
```

MLflow tags are flat, so store the complete hierarchy in
`benchmark.group_path` and indexed levels for filtering. The MLflow run ID is
execution identity; the benchmark ID plus version is definition identity.

## Agents, tools, and data providers

Define an immutable `AgentDefinition` containing stable ID, version,
description, input/output schemas, prompt reference, tool declarations, and
framework metadata. Define an `AgentRuntime` port that invokes a definition and
returns a domain `AgentResult`. Framework-specific agents are adapter concerns.

An agent package owns its instructions and domain-specific tool declarations.
A tool should:

- expose typed input and output schemas;
- depend on a narrow port rather than a database SDK;
- declare timeout, retry, idempotency, and side-effect behavior;
- emit a trace span with redacted arguments and correlation IDs;
- receive authorization context explicitly.

`DatasetProvider` and narrower query or object-reader ports provide actual
data. Databricks, Snowflake, and OMS adapters implement those ports. Unit tests
inject in-memory fakes; contract tests run the same behavioral suite against
fakes and real adapters. Reusable fakes belong under `tests/fakes/`, not in
each production agent. Public synthetic samples may live with benchmark public
assets.

## MLflow traces, evaluations, and artifacts

Instrument model calls, retrieval, tools, guardrails, and evaluator steps.
Prefer MLflow's supported framework instrumentation and add manual spans at
domain boundaries. Preserve OpenTelemetry-compatible trace context so a
different exporter can be introduced later.

Inspect AI should execute tasks and deterministic scorers. The MLflow adapter
records the resulting metrics, traces, and reports. MLflow native or
judge-based scorers may supplement deterministic scoring, but every scorer
must have an ID, version, configuration, and explanation artifact.

Attach human or automated failure reviews as MLflow assessments associated
with the trace. Also write low-cardinality summary tags such as
`failure.kind` and `review.status` for search. Do not put full errors, prompts,
or reviewer notes in tags.

Use a deterministic artifact layout:

```text
inputs/         redacted inputs and dataset lineage
predictions/    structured outputs
evaluation/     scores, explanations, and comparisons
traces/         exports when required for portability
environment/    lock hash, image digest, and runtime metadata
reports/        human-readable summaries
```

MLflow should be the canonical run store. Do not restore a parallel custom
SQLite run database. A local index or cache is acceptable only if it is
rebuildable from MLflow and clearly non-authoritative.

## Hidden answers and security

Hidden answers must not live in `src/`, wheels, agent containers, public
artifacts, prompts, traces, or agent-readable mounts. Store them in an
access-controlled external dataset/artifact location. The public manifest
contains only an opaque URI, revision, and digest.

Run the agent and evaluator with separate identities. The agent receives public
inputs; only the evaluator can resolve hidden answers. Redact credentials,
personal data, prompts, query results, and tool arguments before MLflow
logging. Treat model and agent artifacts as executable supply-chain content.

## Configuration, secrets, and connector ownership

Checked-in configuration contains schemas and non-secret example profiles
only. Load settings at the composition boundary with precedence such as CLI
arguments, environment variables, profile file, then defaults. Resolve secret
references through a `SecretProvider` port backed by environment variables,
the OS keychain, or an enterprise secret manager.

Connector adapters own provider SDK usage, authentication shape, retries,
timeouts, pagination, and provider-specific configuration validation:

- `adapters/data/databricks.py`
- `adapters/data/snowflake.py`
- `adapters/data/oms.py`
- `adapters/mlflow/*`

The workspace owns the business operation it needs, such as loading a dataset;
it does not own credentials or SQL-client construction. Never serialize secret
values to MLflow params, tags, traces, or artifacts.

## Local and offline operation

For local development, run the pinned MLflow client/server on loopback with a
SQLite backend and filesystem artifact store. Put mutable state under an
ignored repository `var/mlflow/` directory or an OS user-data directory:

```text
var/mlflow/backend.db
var/mlflow/artifacts/
```

Pin MLflow server/client 3.16.1 and record the `uv.lock` hash. Offline tests use
in-memory data adapters and deterministic agent/model stubs. Integration tests
may start a pinned MLflow container and connector emulators. Runtime databases,
artifacts, caches, downloaded datasets, and credentials do not belong in Git.

## Tests and CLI

Mirror architectural boundaries:

```text
tests/
├── unit/domain/
├── unit/workspaces/data_engineering/
├── contract/ports/
├── integration/adapters/mlflow/
├── integration/adapters/data/
├── e2e/cli/
├── fakes/
└── fixtures/public/
```

Port contract tests should be adapter-independent and run against each adapter
factory. Tests that require credentials or external systems must be explicitly
marked and skipped with an actionable reason when unavailable.

Place Click commands in `src/cli/`. Commands parse input, construct
adapters, invoke one workspace service, and render results. They must not
contain benchmark execution, scoring, SQL, MLflow logging, or secret-loading
logic. Keep `agentbench` as the console entry point for compatibility.

## Registry and versioning

Use separate version domains:

- benchmark manifests: `schema_version`, semantic `benchmark_version`, Git
  source revision, and content digest;
- agents: stable agent ID plus immutable agent version/source revision;
- datasets: stable dataset ID plus immutable revision or digest;
- prompts: MLflow Prompt Registry versions; aliases are mutable promotion
  pointers;
- deployable models/agents: MLflow Model Registry versions and aliases;
- environments: `uv.lock` hash and container digest.

The MLflow Prompt and Model Registries do not replace the benchmark catalog.
Register only deployable artifacts, not every benchmark run. Prefer aliases
such as `candidate` and `champion`; retain immutable version and source-run
lineage beneath them.

## What must not live in `src/`

- MLflow backend databases, artifacts, traces, or generated reports;
- hidden answers, private datasets, production data snapshots, or credentials;
- Dockerfiles, deployment manifests, and connector profile files;
- large public datasets or downloaded Git repositories;
- exploratory notebooks and one-off investigations unrelated to a workspace;
- generated API documentation, caches, wheels, or virtual environments.

Use top-level `containers/`, `deploy/`, `config/`, `docs/`, and ignored `var/`
directories for repository-wide concerns. Put workspace-owned reproducible
analysis in `src/workspaces/<workspace>/investigations/`. Only small,
non-sensitive benchmark manifests, task code, scorers, public fixtures, and
workspace-owned source belong under the installable source tree.

## Suggested implementation order

1. Update packaging and rules for the top-level source packages and MLflow 3.16.1.
2. Add domain identifiers and benchmark manifest validation.
3. Add ports and in-memory fakes with contract tests.
4. Implement local MLflow tracking, tracing, evaluation, and registry adapters.
5. Implement one data-transformation benchmark and one framework-neutral agent.
6. Add real Databricks, Snowflake, and OMS adapters behind optional extras.
7. Add the thin Click composition layer and local MLflow container.
8. Add security, redaction, offline, and end-to-end regression tests.
