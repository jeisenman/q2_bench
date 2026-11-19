---
name: lineage-impact
description: Assess definition staleness and downstream impact between lineage snapshots.
---

# Lineage impact

Identify explicit, immutable base and head snapshot IDs. Call
`impact_of_change`. Report definitions that became stale, downstream nodes,
snapshot pins, and unresolved scope. Use `list_stale_definitions` to find current
approved entries that need review.

Do not report a pass if a source is unavailable or a finding is unresolved.
Do not claim complete repository or runtime coverage.
