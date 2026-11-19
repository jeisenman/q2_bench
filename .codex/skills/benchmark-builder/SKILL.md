---
name: benchmark-builder
description: Turn a captured MLflow trace of a real workflow run into a reviewable benchmark case, preserving every tool call as evidence and injecting plausible irrelevant data as distractors. Use when asked to add a run to a benchmark, build a case from a trace, or grow benchmark coverage.
---

# Benchmark Builder

Build one benchmark case from one captured trace. Use the trace as the source
of truth. Record what occurred. Do not invent case data.

## When to use

Use this after a real workflow run that should become a benchmark. Examples
include production-support investigations and resource lookups. Select runs
whose tool calls and results show behavior to preserve. Both harnesses capture
traces automatically after setup. Check for an existing trace.

## Workflow

1. Identify the trace. Get the trace ID from the user, or list recent traces
   for the experiment. Confirm the correct trace before you continue.

2. Extract the case. This preserves every tool call, its arguments, and its
   result as evidence:

   ```bash
   python3 .codex/skills/benchmark-builder/scripts/build_case.py <trace-id> --output <case-dir>
   ```

3. Review the extracted data before you add distractors. Confirm that the tool
   calls match the run. Confirm that redaction removed all credentials, tokens,
   and raw logs. Stop and report if sensitive data remains.

4. Add distractors. Include plausible, irrelevant records to test whether the
   agent can select the correct evidence. A case with only relevant evidence
   tests recall. Add distractors with:

   ```bash
   python3 .codex/skills/benchmark-builder/scripts/build_case.py <trace-id> --output <case-dir> \
     --distractors 8
   ```

   Distractors must be plausible for the same operational window. Examples
   include neighbouring DAGs, healthy clusters, unrelated clients, and jobs
   that failed for a different reason. Do not use relevant data as a distractor.
   Do not let a distractor contradict recorded evidence.

5. Record observed behavior with `status: candidate_expectation`. Independent
   human review is required. Do not treat candidates as truth. Do not promote
   a candidate to an expectation in the pass that created it.

6. Put the case in the owning workspace benchmark directory. Update its
   `manifest.yaml`. Never edit a benchmark under `deprecated/`. Retired cases
   are source data. Preserve their record of what occurred on that date.

## Rules

- One trace, one case. Do not merge runs.
- Preserve tool-call order and count in the evidence. Record what the run did,
  even when scoring does not require an exact sequence.
- Store minimized, redacted evidence. Never store credentials or raw logs.
- Record distractor counts in the case manifest. The reviewer must be able to
  distinguish evidence from distractors without repeating extraction.
- Include null cases: healthy jobs, pods, and clusters where the correct answer
  is that nothing is wrong.

## Report Shape

- `Trace`: the trace ID and the workflow it captured.
- `Evidence`: tool calls preserved, with counts by tool.
- `Distractors`: how many were injected and of what kind.
- `Review`: what a human must confirm before the case is trusted.
