# Setup

This repository is a set of **workspaces**. A workspace owns the skills, the
MCP tool bindings, and the benchmarks for one domain. You are either Claude or
Codex; the steps below differ by harness, so follow your own section.

Everything here assumes local operation: a loopback MLflow server with a SQLite
backend and a filesystem artifact store. Nothing requires a shared service.

## The model

```text
claude / codex          the agent loop — not defined in this repository
      │ invokes
      ▼
workspace skills        baseline procedures: "do production support"
      │ calls
      ▼
MCP servers             typed, authenticated tools
      ▲
benchmarks              score the harness + skill + MCP together
```

Skills live with their workspace, at
`src/workspaces/<workspace>/skills/<skill-id>/`. Harness directories
(`.claude/skills/`, `.codex/skills/`) are **generated**. Never edit them
directly — `scripts/check_skills.py` fails the build when they drift from the
workspace source.

## Common steps

```bash
uv sync
uv run agentbench sync-skills
```

`sync-skills` reads every `src/workspaces/*/skills/*/skill.yaml` and renders
each skill into the directories of the harnesses it declares. Per-harness
overlay files live under `harness/<name>/` in the skill source and are merged
in only for that harness. The `{{SKILL_DIR}}` token is replaced with the path
the skill occupies in that harness, so script invocations resolve correctly on
both sides.

Files listed under `state:` in a skill manifest are seeded once and then owned
by the harness at runtime. They survive re-syncs and are excluded from drift
checks, so using a skill never fails the quality gate.

Verify:

```bash
uv run agentbench sync-skills --check
```

## Working in a workspace

Pick the workspace whose domain you are in, then read, in order:

1. `src/workspaces/<workspace>/skills/` — what procedures already exist.
2. `src/workspaces/<workspace>/benchmarks/` — what behavior is scored.
3. `src/workspaces/<workspace>/benchmarks/deprecated/` — retired cases kept as
   source data. Read them for evidence; never edit them to match new
   expectations.

A skill declares the MCP server and tools it needs in its `skill.yaml`. If
those tools are not connected, say so and stop rather than approximating the
work with shell commands.

## Claude

Claude discovers skills from `.claude/skills/`. After `sync-skills`, the
workspace skills are available by name.

Enable trace capture so runs can become benchmark cases:

```bash
mlflow autolog claude
```

Check or disable it:

```bash
mlflow autolog claude --status
```

```bash
mlflow autolog claude --disable
```

Claude does not read `harness/codex/` overlays. Anything Claude-specific for a
skill belongs in `harness/claude/` in that skill's source.

## Codex

Codex discovers skills from `.codex/skills/`. The `harness/codex/` overlay
supplies `agents/openai.yaml`, which gives the skill its display name and
default prompt in the Codex interface.

Install the MLflow tracing hook, globally or per-invocation:

```bash
npm install -g @mlflow/codex
```

```bash
npx @mlflow/codex setup
```

Then run the interactive configuration:

```bash
mlflow-codex setup
```

This repository can also write the Codex notify hook directly, which is useful
when pinning a specific tracking URI and experiment:

```bash
uv run agentbench configure-codex-tracing --tracking-uri sqlite:///var/mlflow/backend.db
```

That writes `notify = ["mlflow-codex", "notify-hook"]` into your Codex
`config.toml` and records the destination in `.codex/mlflow-tracing.json`. It
refuses to overwrite an existing notify hook, so merge by hand if you already
have one.

## Traces become benchmarks

Trace capture is not observability for its own sake. A captured trace is the
only trustworthy source for a new benchmark case, because it records the tool
calls that actually happened rather than the ones someone remembered.

The loop:

1. Run a workflow through your harness. The hook captures the trace.
2. Invoke the `benchmark-builder` skill with the trace ID.
3. It preserves every tool call as evidence and injects plausible irrelevant
   records as distractors, so the case rewards selecting the right evidence
   rather than reading everything.
4. Observed behavior is written as `candidate_expectation` and requires
   independent human review before it is trusted.

## Adding a skill

```text
src/workspaces/<workspace>/skills/<skill-id>/
├── skill.yaml        id, workspace, harnesses, MCP tools, env, state files
├── SKILL.md          the procedure, using {{SKILL_DIR}} for script paths
├── scripts/          helpers the harness runs directly
├── references/       lookup data
└── harness/
    ├── claude/       files merged only into .claude/skills/<skill-id>/
    └── codex/        files merged only into .codex/skills/<skill-id>/
```

`id` must match the directory name, and must be unique across all workspaces:
harness skill directories are flat, so two workspaces cannot export the same
skill name. The sync fails with both source paths when they collide.

Then run `uv run agentbench sync-skills` and commit both the source and the
generated output.

## Quality gate

```bash
uv run python scripts/check.py
```

This runs formatting, lint, typing, tests, the file-length limit, the agent
documentation policy, and the skill sync check.
