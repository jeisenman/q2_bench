# Lineage workflow ownership

Production lineage code is Go. The previous Python extraction package has
been removed. Use these maintained packages:

- `workflows/lineage`: provider-neutral read-only graph queries.
- `workflows/lineagecheck`: local reviewed source contracts, literal schema
  extraction, immutable snapshots, PR compatibility, and backfill coverage.
- `workflows/semanticsync`: optional validated Researcher snapshot ingestion.
- `mcpapi/lineage*.go`: composition through the existing lineage MCP surface.

Workflow guidance lives in
`src/workspaces/data_engineering/skills/lineage-review/`. See `docs/lineage.md`
for source ownership, evidence limits, CLI commands, and runtime selection.
Do not restore a Python lineage runtime or import protected Researcher code.
