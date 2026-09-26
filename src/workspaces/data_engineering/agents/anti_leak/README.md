# Anti-leak agent

The anti-leak agent audits sanitized container snapshots for exposed data and
weak security profiles. It never scans the host directly.

Version 1 is intentionally poor so later versions can be evaluated against the
same benchmark. It detects only:

- execution as root;
- visible files named `.env`.

It intentionally misses environment-secret values, host credential mounts,
Docker socket exposure, writable roots, excessive Linux capabilities, and
benchmark-answer leakage.

```python
import asyncio

from domain import AgentRequest
from workspaces.data_engineering.agents.anti_leak import AntiLeakAgent

result = asyncio.run(
    AntiLeakAgent(source).run(
        AgentRequest(prompt="Audit the container.", correlation_id="audit-1")
    )
)
```

The benchmark records these misses as the v1 baseline. Future versions should
add one evidence-backed capability at a time and rerun the unchanged case.
