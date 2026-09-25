# OpenAI Agents SDK

Reviewed: 2026-09-24

This is a repository-focused guide to the official OpenAI Agents SDK. Consult
the canonical documentation for current API details.

Canonical documentation:

- <https://developers.openai.com/api/docs/guides/agents-sdk>
- <https://developers.openai.com/api/docs/guides/agents/quickstart>

## Installation

The official Python package is installed with:

```bash
uv add openai-agents
```

Its Python import namespace is `agents`:

```python
from agents import Agent, Runner
```

This repository's own package uses the `agentsdk` namespace. Keep imports
explicit so the local vector library and the upstream orchestration SDK remain
clearly separated.

## Smallest useful agent

The official quickstart begins with one focused agent and one run:

```python
import asyncio

from agents import Agent, Runner


async def main() -> None:
    agent = Agent(
        name="Assistant",
        instructions="Answer clearly and concisely.",
    )
    result = await Runner.run(agent, "Summarize the request.")
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
```

Model availability and defaults can change. Select a model through application
configuration instead of embedding model names throughout domain code.

## Core concepts

### Agents

An agent combines instructions, a model configuration, and capabilities.
Keep instructions narrow and testable. Construct agents at the application
boundary rather than as import-time global state.

### Runs

`Runner` executes an agent turn and returns a result containing final output
and run history. Prefer asynchronous execution in applications that perform
network or tool I/O.

### Tools

Tools expose application behavior to a model. Tool functions should:

- Have typed inputs and outputs.
- Validate permissions and domain constraints.
- Be small wrappers over separately testable services.
- Avoid hidden global state.
- Return concise, structured results.

### Handoffs

Handoffs delegate work to specialized agents. Use them only when specialization
or ownership boundaries are clearer than a single agent with tools.

### Guardrails

Guardrails validate input or output around execution. They complement, but do
not replace, authorization, domain validation, and deterministic application
checks.

### Sessions

Sessions preserve conversation state across turns. Keep durable business state
outside conversation history, with explicit persistence and retention rules.

### Tracing

Tracing records agent runs, model calls, tools, and handoffs for debugging.
Never attach secrets or unnecessary sensitive data to trace metadata.

## Integration pattern for this repository

Provider integration should live in a future module such as:

```text
src/agentsdk/integrations/openai/
```

That module may depend on `agents`. Existing vector modules must remain usable
without an API key or provider dependency.

Recommended boundary:

```python
from typing import Protocol

import numpy as np
from numpy.typing import NDArray


class Embedder(Protocol):
    async def embed(self, texts: tuple[str, ...]) -> NDArray[np.float64]:
        """Return one vector per input text."""
        ...
```

The provider adapter owns batching, retries, and response conversion. The local
vector index owns validation, normalization, and similarity ranking.

## Testing guidance

- Unit-test tools as ordinary Python functions.
- Replace network-facing runners and clients with typed fakes.
- Assert handoff and guardrail decisions separately from generated wording.
- Keep end-to-end tests optional and credential-gated.
- Never require an API key for the default quality command.
