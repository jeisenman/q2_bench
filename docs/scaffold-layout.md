# Benchmark scaffold layout

The repository keeps benchmark definitions and runtime resources close to the
source tree while leaving the existing `agentsdk` package unchanged.

Inspect AI is the canonical benchmark runner. Run the smoke benchmark with:

```bash
uv run inspect eval src/benchmarks/benchmark1/task.py
```

```text
src/
  agentsdk/                  Agent contracts, traces, storage, CLI, vectors
  benchmarks/
    benchmark1/              Minimal benchmark example
    benchmarkn/              Larger benchmark template
      manifest.yaml          Source repository and execution contract
      assets/                Public inputs and fixtures
      rubric/                Scoring criteria
      hidden/                Protected expected answers
  investigations/            Reproducible analysis notes
  resources/
    manifest.yaml            External repository pointers
    Dockerfile               Local benchmark container example
    connectors/              Databricks, Snowflake, and OMS config examples
```

## Manifest conventions

Benchmark manifests pin a repository URL and revision, then point to the
asset, rubric, and hidden-answer paths. Resource manifests describe shared
repositories and the container/connectors used to execute them. Revisions
should be immutable tags or commit SHAs in production.

## Safety conventions

The checked-in connector files contain environment-variable names only. Inject
credentials at runtime, never into YAML. Treat `hidden/` as access-controlled
data and do not publish its contents with public benchmark assets.

## Local run workflow

The `agentbench` command stores runs in `.agentsdk/runs.db` by default:

```bash
uv run agentbench create-benchmark my-benchmark \
  --repository-url https://github.com/example/project.git \
  --revision COMMIT_SHA \
  --description "Evaluate the project task."
uv run agentbench benchmarks
uv run agentbench connectors
uv run agentbench runs
uv run agentbench trace RUN_ID
uv run agentbench annotate RUN_ID \
  --category correctness \
  --message "The response omitted the required evidence."
```

Agents implement the typed `Agent` protocol and expose an `AgentDefinition`.
`LocalAgentRunner` records the request, response or exception, and structured
trace events. Failed runs accept multiple human annotations.
