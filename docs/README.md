# Local documentation

This directory is the agent-readable entry point for the project.

## Start here

- [Project architecture](architecture.md)
- [Proposed source architecture](source-architecture-proposal.md)
- [MLflow 3.16.1 local guide](mlflow/README.md)
- [Prod-support benchmark](prod-support-benchmark.md)
- [Benchmark scaffold](scaffold-layout.md)
- [OpenAI Agents SDK](openai-agents-sdk.md)
- [Vector search](vector-search.md)

## Documentation policy

- Keep each document focused and below 400 lines.
- Describe repository-specific decisions locally.
- Link to canonical upstream documentation for APIs that can change.
- Include a `Reviewed` date on summaries of external documentation.
- Update documentation and tests in the same change as behavior.

The repository package is named `agentsdk`. The official OpenAI Agents SDK
Python package is a separate dependency named `openai-agents` and is imported
as `agents`. Do not confuse their public APIs.
