# Prod-support evolution agent

This agent is instructional: it explains how the production-support prompt
became safer and more reliable as real failures exposed missing constraints.

The earliest agent-related commit in `pl-data-plugins` is:

- Commit: `c11a9a7e73abaf496520594af0e6e50258f4d069`
- Date: 2026-08-04
- Author: Jordan Eisenman
- Subject: `Current`

That commit contains two firsts:

1. The first literal prompt file, `.codex/prompts/setup.md`.
2. The first prod-support agent prompt,
   `.codex/skills/prod-support/SKILL.md`.

The first prod-support prompt already established discovery, specialist
investigation, client mapping, a channel report, production safety, and
reflection. It also contained useful early weaknesses: an incomplete workflow
list, duplicate EventBus sections, mixed policy and implementation, and rules
that were not yet tied to benchmark evidence.

Use the agent to render the chronological comparison:

```python
import asyncio

from domain import AgentRequest
from workspaces.data_engineering.agents.prod_support_evolution import (
    ProdSupportEvolutionAgent,
)

result = asyncio.run(
    ProdSupportEvolutionAgent().run(
        AgentRequest(
            prompt="Show how prod support evolved.",
            correlation_id="example",
        )
    )
)
print(result.output)
```
