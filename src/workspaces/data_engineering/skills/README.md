# Data-engineering skills

Baseline procedures the harness runs. Each skill is owned by this workspace and
generated into `.claude/skills/` and `.codex/skills/` by
`uv run agentbench sync-skills`.

Do not edit the generated harness copies. `scripts/check_skills.py` fails when
they drift from these sources, and reports which file and which command fixes
it.

| Skill | Purpose | Harnesses |
| --- | --- | --- |
| `resource-discovery` | Query PrecisionLender Resource Discovery for client and resource metadata. | claude, codex |
| `benchmark-builder` | Turn a captured trace into a reviewable benchmark case with distractors. | claude, codex |
| `prod-support` | Discover, triage, and remediate production Airflow failures across US and CA. | claude, codex |
| `upgrade-dependencies` | Research, implement, and verify Python and container dependency upgrades. | claude, codex |

`prod-support` was absorbed from `pl-data-plugins` and is now owned here.
Its `scripts/` run directly; `references/mcp-tools.md` describes the
`prod-support` MCP server, which is preferred when connected.

See [SETUP.md](../../../../SETUP.md) for the layout of a skill directory and
the rules the sync enforces.
