---
name: prodscreen
description: Perform production Airflow support using visible Chrome control, including scoped EventBus recovery and downstream rerun planning when requested.
---

# Production support with screen control

Follow [prod-support](../prod-support/SKILL.md) and the procedures it references
for the operational window, evidence, classification, reporting, and recovery
guards. Use these changes to the interaction model:

- Use the supported Chrome browser-tab control for visible Airflow and
  application interactions. Read exact identities and logs from the typed
  connectors when available. Compare them with both regional UI inventories.
- If `kubectl` is unavailable, delegate the relevant screen inspection to a
  Terra subagent using visible Chrome control. Reconcile its evidence with the
  exact task and run. Report any required pod or overlap evidence that the
  available screens cannot establish. Continue within the user's authorized scope.
- In each displayed failed-task log, use Command-F to find `Distinctness
  validation failed for` and inspect each match, including the dataset name.
  Match the exact dataset to its proven upstream producer and run before
  you choose a rerun. A search match alone does not establish its scope.
- For client and production PLApp routing, look up the complete provisioned
  UUID first in the local resource-discovery client directory. Use the
  Resource Discovery browser console for missing or ambiguous entries and
  verify that its provisioned UUID matches exactly. Never infer a production
  environment from a staging entry, Airflow region, name, or partial UUID.
- The requesting user may direct Terra subagents to inspect independent screens
  or prepare a browser-control procedure. Keep at most three agents active,
  retain the incident ledger centrally, and reconcile their evidence before
  any production action. Do not allow concurrent resends to bypass the global
  10-second spacing requirement.
- Keep each requested resend or rerun within its proven, authorized scope.
  Apply the exact-client, environment, recoverability, DAG, state, dependency,
  and read-back guards in the original procedures.
- For repeated agent, implementation, review, or retry loops, first establish
  the objective and success measure, intended change, component dependencies,
  and required systems with the user, and obtain their scope confirmation.

Produce the prod-support message before requested remediation when the user
asks for the report first. Do not post the message without authorization.
For a verified, authorized opportunity resend batch, the copyable
[browser snippet](scripts/resend_one_batch.js) submits only that batch and
leaves its confirmation for inspection.
