# One-pass Zendesk dataset draft study

This investigation checks whether an existing dataset definition can gain useful
Zendesk article links without changing its technical scope or adding documentation
audit prose. The unit is a logical dataset; linked jobs, fields, copies, source
pins and definitions stay with that dataset.

The completed run accounts for 553 selected datasets. Each received one
`gpt-6-luna` edit pass through the Codex CLI harness. Static checks accepted 491
changed drafts and held 62 outputs. No model retry or second model review ran.
The changed count includes removal of old audit prose. Held outputs were not
applied. The [sanitized summary](run-summary.json) contains aggregate results.

Dataset drafts, rejected outputs, model inputs, source snapshots and the full
article corpus remain local. This repository contains tooling and aggregate
results only. No draft runtime import, graph update, formal definition submission,
publication of dataset text or SME approval was performed.

## Procedure

1. Validate and synchronize the explicitly pinned published source generation.
2. Freeze the selected dataset IDs and source graph. Join exact namespace/name
   identities; never substitute labels, jobs, fields or guessed copy identities.
3. Validate the complete approved corpus and its article/chunk identities, original
   URLs, filter policy and content hashes. Retrieve candidates from the full corpus.
4. Record safe audit-only cleanup spans. Keep mixed passages intact for the same
   single Luna pass under the separately pinned caller policy.
5. Freeze all inputs and hashes. Retain complete source evidence locally; record
   any bounded model-context projection explicitly.
6. Run one ephemeral, read-only Codex invocation per target. An exclusive attempt
   marker prevents a second pass, including after interruption.
7. Check output identity, definition shape, existing technical literals/numbers,
   source URLs, supplied citation URLs, audit text and placeholders. Hold failures.
8. Reconcile every selected ID and generate a local review index with provenance.

The original [prompt 2.0.0](prompts/2.0.0.md) is immutable. A separate versioned
caller policy permits the same pass to remove mixed audit clauses while retaining
technical details and useful citations. If no article is relevant, audit removal
is the only allowed change.

## Commands

All commands use explicit, approved local inputs. Inspect `--help` before running.
Preparation validates this study's source generation and prompt pins; it never
fetches production data. The run output directory must be new.

```sh
go run ./src/workspaces/data_engineering/investigations/zendesk_dataset_rollout_20261119/prepare --help
go run ./src/workspaces/data_engineering/investigations/zendesk_dataset_rollout_20261119/execute --help
go run ./src/workspaces/data_engineering/investigations/zendesk_dataset_rollout_20261119/report --help
```

`execute` defaults to input validation. `--execute` dispatches the authorized
calls, with a positive parallel limit and per-call deadline. Completed attempts
are skipped; unresolved attempts block another dispatch. Artifact-only
`--revalidate-held` cannot dispatch models and can run only once per held result.
It preserves the original result/hash and raw output. It corrects guard handling
of redundant audit identity metadata and Markdown code formatting; it does not
edit definition values or accept other violations.

The private report records before/prepared/draft hashes, exact identities, source
and prompt pins, caller policy, retrieval evidence, CLI run identity and usage.
Cited chunk IDs identify supplied chunks for a cited article URL; they are not
per-claim proof or a support verdict.

## Package boundaries and checks

- `contract/`: stdlib-only HTTP wire DTOs for the offline investigation.
- `prepare/`: strict identity/corpus validation, context preparation and retrieval.
- `execute/`: fixed single-pass dispatch through the Codex CLI harness.
- `report/`: deterministic artifact reconciliation and split local review indexes.

The tools do not import Researcher implementation, serve semantic meaning,
configure MCP, or replace the existing lineage service. Model-context inventories
omitted from the request remain in complete, hash-pinned local evidence. No claim
is made that the model read omitted content or established an exact dataset-to-
notebook execution mapping.

Run the investigation tests and repository checks:

```sh
go test ./src/workspaces/data_engineering/investigations/zendesk_dataset_rollout_20261119/...
uv run python scripts/check.py
```

Synthetic tests cover success, boundary and failure cases. A separate opt-in,
read-only parity check reproduced all 553 frozen target artifacts byte-for-byte,
including their fields, linked jobs and source pins. Static checks do not replace
SME review, prove runtime equivalence or certify complete lineage coverage.

Created with Codex, with `gpt-6.1-sol` implementation assistance and
`gpt-6-luna` dataset edit passes.
