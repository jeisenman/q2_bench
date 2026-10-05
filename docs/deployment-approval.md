# Deployment approval command

`agentbench approve-deployment` approves one Azure DevOps deployment approval
by its exact numeric approval ID. It is an explicit operator action; it is not
called from the deployment pipeline itself.

Set the Azure DevOps personal access token only in the current shell:

```bash
export AZDO_PAT='...'
```

Approve the pending step:

```bash
uv run agentbench approve-deployment <approval-id>
```

The command defaults to the `precisionlender` organization and `Data
Engineering` project. Override them when needed:

```bash
uv run agentbench approve-deployment <approval-id> \
  --organization precisionlender \
  --project "Data Engineering" \
  --comment "Reviewed Alpha deployment."
```

The command sends only the approval ID, approved status, and audit comment.
The token is never printed or written to repository files.
