---
name: benchmark-builder
description: Turn a captured MLflow trace of a real workflow run into a reviewable benchmark case, preserving every tool call as evidence and injecting plausible irrelevant data as distractors. Use when asked to add a run to a benchmark, build a case from a trace, or grow benchmark coverage.
---

# Benchmark Builder

Build one benchmark case from one captured trace. A case is only useful if it
records what actually happened, so the trace is the source of truth and nothing
in a case may be invented.

## When to use

Use this after a real workflow run that is worth keeping: a production-support
investigation, a resource lookup, anything where the tool calls and their
results describe behavior you want to hold steady. Both harnesses capture
traces automatically once set up, so there is usually a trace waiting.

## Workflow

1. Identify the trace. Take the trace ID from the user, or list recent traces
   for the experiment and confirm the right one before continuing.

2. Extract the case. This preserves every tool call, its arguments, and its
   result as evidence:

   ```bash
   python3 .claude/skills/benchmark-builder/scripts/build_case.py <trace-id> --output <case-dir>
   ```

3. Review what was extracted before adding distractors. Confirm the tool calls
   match what the run actually did, and that no credential, token, or raw log
   survived redaction. Stop and report if anything sensitive is present.

4. Add distractors. A case that contains only relevant evidence tests recall,
   not discrimination — the agent cannot be wrong by reading everything. Inject
   plausible but irrelevant records so the case rewards selecting the right
   evidence:

   ```bash
   python3 .claude/skills/benchmark-builder/scripts/build_case.py <trace-id> --output <case-dir> \
     --distractors 8
   ```

   Distractors must be plausible for the same operational window: neighbouring
   DAGs, healthy clusters, unrelated clients, jobs that failed for a different
   reason. Never make a distractor that is actually relevant, and never let a
   distractor contradict recorded evidence.

5. Record expectations as candidates, not truth. Observed behavior becomes
   `status: candidate_expectation` and requires independent human review. Do
   not promote a candidate to an expectation in the same pass that created it.

6. Place the case under the owning workspace benchmark directory and update its
   `manifest.yaml`. Never edit a benchmark beneath `deprecated/` — retired
   cases are source data, and rewriting them destroys the record of what
   happened on that date.

## Rules

- One trace, one case. Do not merge runs.
- Preserve tool-call ordering and cardinality in the evidence; the case records
  what the run did, even when scoring does not assert an exact sequence.
- Store minimized, redacted evidence. Never store credentials or raw logs.
- Distractor counts belong in the case manifest so a reviewer can tell signal
  from noise without re-running extraction.
- Include null cases: healthy jobs, pods, and clusters where the correct answer
  is that nothing is wrong.

## Report Shape

- `Trace`: the trace ID and the workflow it captured.
- `Evidence`: tool calls preserved, with counts by tool.
- `Distractors`: how many were injected and of what kind.
- `Review`: what a human must confirm before the case is trusted.
