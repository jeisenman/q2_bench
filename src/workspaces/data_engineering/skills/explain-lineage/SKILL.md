---
name: explain-lineage
description: Explain a job, dataset, or column using the local lineage service and source-pinned evidence.
---

# Explain lineage

Use the existing lineage search to find the requested job, dataset, or column.
Set an explicit namespace, name, and optional column. Call `explain_node` with
that identity.

Keep these distinctions clear:

- Physical locations and logical names.
- Approved SME meaning and machine-generated text.
- Missing or stale data and verified facts.

Include snapshot pins and unresolved coverage in the answer. Get the formal
definition only when the user explicitly requests it. Do not infer a definition.
